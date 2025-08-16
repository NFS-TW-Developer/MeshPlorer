import asyncio
import logging
import random
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from app.utils.ConfigUtil import ConfigUtil
from app.utils.CwaUtil import CwaUtil
from app.utils.MeshSightUtil import MeshSightUtil
from app.services.MeshtasticService import MeshtasticService


class WeatherService:
    """天氣服務，負責處理天氣查詢和回應"""
    
    def __init__(self, meshtastic_service: MeshtasticService):
        self.config = ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())
        self.meshtastic_service = meshtastic_service
        self.weather_silence_until: datetime = datetime.now(timezone.utc)
        
    async def handle_weather_request(
        self, 
        mp: Any, 
        channel_id: int, 
        sender_tag: str
    ) -> None:
        """處理天氣查詢的請求"""
        try:
            # 檢查靜默期間
            if self.weather_silence_until > datetime.now(timezone.utc):
                self.logger.info(
                    f"尚未到天氣查詢的靜默截止時間: "
                    f"now: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}, "
                    f"silence_until: {self.weather_silence_until.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                # 發送靜默的 emoji
                await self._send_silence_emoji(mp, channel_id)
                return
                
            # 設定靜默期間
            self.weather_silence_until = datetime.now(timezone.utc) + timedelta(minutes=1)
            
            # 取得位置資訊
            city, district = await self._get_location_info(mp)
            
            if not city or not district:
                await self._send_no_location_response(mp, channel_id, sender_tag)
                return
                
            # 發送處理中的訊息
            response_packet = await self._send_processing_message(mp, channel_id, sender_tag)
            
            # 查詢天氣資料
            weather_data = await CwaUtil().get_cwa_data_fd0047093(
                location_name=city,
                location_district=district,
            )
            
            await asyncio.sleep(random.uniform(0.5, 1))
            
            if weather_data:
                await self._send_weather_data(
                    weather_data, city, district, response_packet, channel_id
                )
            else:
                await self._send_weather_error(response_packet, channel_id, sender_tag)
                
        except Exception as e:
            self.logger.error(f"處理天氣請求時發生錯誤: {e}")
            
    async def _get_location_info(self, mp: Any) -> tuple[Optional[str], Optional[str]]:
        """取得位置相關資訊"""
        try:
            node_position = await MeshSightUtil().get_node_position(getattr(mp, "from"))
            if node_position and node_position.get("position"):
                taiwan_address = node_position.get("position", {}).get("taiwanAddress")
                if taiwan_address and isinstance(taiwan_address, dict):
                    city = taiwan_address.get("cityOrCounty")
                    district = taiwan_address.get("districtLevel")
                    return city, district
        except Exception as e:
            self.logger.error(f"取得位置資訊時發生錯誤: {e}")
        return None, None
        
    async def _send_silence_emoji(self, mp: Any, channel_id: int) -> None:
        """發送靜默的 emoji"""
        packet = self.meshtastic_service.create_emoji_packet(
            channel_id=channel_id,
            emoji="🤐",
            reply_id=getattr(mp, "id", None)
        )
        await self.meshtastic_service.send_packet(
            mesh_packet=packet,
            destination_id="^all"
        )
        
    async def _send_no_location_response(self, mp: Any, channel_id: int, sender_tag: str) -> None:
        """發送無位置資訊的回應"""
        packet = self.meshtastic_service.create_text_packet(
            channel_id=channel_id,
            text=f"嗨！{sender_tag}，我無法查詢天氣，因為沒有您所在位置的資訊。",
            reply_id=getattr(mp, "id", None)
        )
        await self.meshtastic_service.send_packet(
            mesh_packet=packet,
            destination_id="^all",
            want_ack=True
        )
        
    async def _send_processing_message(self, mp: Any, channel_id: int, sender_tag: str) -> Any:
        """發送處理中訊息"""
        packet = self.meshtastic_service.create_text_packet(
            channel_id=channel_id,
            text=f"嗨！{sender_tag}，正在為您查詢天氣，若未收到回應，請稍後再試。",
            reply_id=getattr(mp, "id", None)
        )
        return await self.meshtastic_service.send_packet(
            mesh_packet=packet,
            destination_id="^all",
            want_ack=True
        )
        
    async def _send_weather_data(
        self, 
        weather_data: Dict, 
        city: str, 
        district: str, 
        response_packet: Any, 
        channel_id: int
    ) -> None:
        """發送天氣資料"""
        # 發送第一段天氣資訊
        summarize_1 = CwaUtil().summarize_weather_descriptions(weather_data, limit=1, offset=0)
        if summarize_1:
            packet = self.meshtastic_service.create_text_packet(
                channel_id=channel_id,
                text=f"{city}{district} {summarize_1}",
                reply_id=getattr(response_packet, "id", None)
            )
            await self.meshtastic_service.send_packet(
                mesh_packet=packet,
                destination_id="^all",
                want_ack=True
            )
            
        await asyncio.sleep(random.uniform(0.5, 1))
        
        # 發送第二段天氣資訊
        summarize_2 = CwaUtil().summarize_weather_descriptions(weather_data, limit=1, offset=1)
        if summarize_2:
            packet = self.meshtastic_service.create_text_packet(
                channel_id=channel_id,
                text=f"{city}{district} {summarize_2}",
                reply_id=getattr(response_packet, "id", None)
            )
            await self.meshtastic_service.send_packet(
                mesh_packet=packet,
                destination_id="^all",
                want_ack=True
            )
            
    async def _send_weather_error(self, response_packet: Any, channel_id: int, sender_tag: str) -> None:
        """發送天氣查詢錯誤訊息"""
        packet = self.meshtastic_service.create_text_packet(
            channel_id=channel_id,
            text=f"嗨！{sender_tag}，我暫時無法查詢天氣，請稍後再試。",
            reply_id=getattr(response_packet, "id", None)
        )
        await self.meshtastic_service.send_packet(
            mesh_packet=packet,
            destination_id="^all",
            want_ack=True
        )
