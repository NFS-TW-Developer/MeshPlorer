import asyncio
import logging
import random
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from app.utils.ConfigUtil import ConfigUtil
from app.utils.MeshSightUtil import MeshSightUtil
from app.utils.MeshtasticUtil import MeshtasticUtil
from app.services.MeshtasticService import MeshtasticService


class EmergencyGuardianService:
    """緊急守護服務，負責處理緊急相關訊息"""
    
    def __init__(self, meshtastic_service: MeshtasticService):
        self.config = ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())
        self.meshtastic_service = meshtastic_service
        self.emergency_silence_until: datetime = datetime.now(timezone.utc)
        self.seen_message_ids = {}  # id: timestamp
        self.seen_message_expire = 600  # 秒，保留 10 分鐘
        
    async def handle_emergency_message(self, mp: Any, topic: str) -> None:
        """處理緊急守護相關訊息"""
        try:
            # 檢查靜默期間
            if datetime.now(timezone.utc) < self.emergency_silence_until:
                self.logger.info(
                    f"尚未到緊急回應的靜默截止時間，忽略本次，"
                    f"now: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}, "
                    f"silence_until: {self.emergency_silence_until.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                return
            else:
                # 設定緊急回應的靜默截止時間
                self.emergency_silence_until = datetime.now(timezone.utc) + timedelta(minutes=3)
                
            # 檢查重複的訊息
            if not await self._check_duplicate_message(mp):
                return
                
            self.logger.info(
                f"處理緊急守護訊息，msg_id: {getattr(mp, 'id', 0)}, "
                f"sender: {getattr(mp, 'from')}, topic: {topic}, "
                f"mp: {str(mp).replace('\n', ' ')}"
            )
            
            # 解析訊息的內容
            text = await self._extract_message_text(mp)
            if not text:
                return
                
            # 取得位置相關資訊
            node_position = await self._get_node_position(mp)
            
            # 製作發送者標籤和緊急地址資訊
            sender_tag, emergency_address = await self._create_sender_info(mp, node_position)
            
            # 發送緊急守護相關訊息
            await self._send_emergency_notification(
                topic, sender_tag, emergency_address, text
            )
            
        except Exception as e:
            self.logger.error(f"處理緊急守護訊息時發生錯誤: {e}")
            
    async def _check_duplicate_message(self, mp: Any) -> bool:
        """檢查重複的訊息"""
        now = time.time()
        # 清理過期的訊息 ID
        expired = [
            mid for mid, ts in self.seen_message_ids.items()
            if now - ts > self.seen_message_expire
        ]
        for mid in expired:
            del self.seen_message_ids[mid]
            
        if getattr(mp, "id", 0) is not None:
            if getattr(mp, "id", 0) in self.seen_message_ids:
                self.logger.info(f"訊息 {getattr(mp, 'id', 0)} 已處理過，忽略重複處理")
                return False
            self.seen_message_ids[getattr(mp, "id", 0)] = now
        return True
        
    async def _extract_message_text(self, mp: Any) -> Optional[str]:
        """提取訊息的文字內容"""
        decode = getattr(mp, "decoded", None)
        if decode is None:
            self.logger.error(f"訊息 {getattr(mp, 'id', 0)} 沒有解碼資料，無法進行處理")
            return None
            
        # 忽略 emoji 類型的訊息
        if getattr(decode, "emoji", 0) == 1:
            self.logger.info(
                f"收到來自緊急守護頻道的 emoji 訊息，msg_id: {getattr(mp, 'id', 0)}，"
                f"sender: {getattr(mp, 'from')}"
            )
            return None
            
        # 提取文字訊息
        if (hasattr(decode, "payload") and 
            isinstance(decode.payload, bytes) and 
            decode.payload):
            try:
                text = decode.payload.decode("utf-8")
                return text.strip() if text else None
            except Exception:
                return None
        else:
            self.logger.info(f"訊息 {getattr(mp, 'id', 0)} 沒有 payload，無法處理")
            return None
            
    async def _get_node_position(self, mp: Any) -> Optional[Dict]:
        """取得節點位置"""
        try:
            node_position = await MeshSightUtil().get_node_position(getattr(mp, "from"))
            self.logger.info(f"get_node_position 結果: {node_position}")
            return node_position
        except Exception as e:
            self.logger.error(f"get_node_position 發生例外: {e}")
            return None
            
    async def _create_sender_info(self, mp: Any, node_position: Optional[Dict]) -> tuple[str, Optional[str]]:
        """創建發送者資訊"""
        sender_tag = f"!{MeshtasticUtil.convert_node_id_from_int_to_hex(getattr(mp, 'from'))}"
        emergency_address = None
        
        if (node_position and 
            node_position.get("position") and 
            node_position["position"].get("taiwanAddress")):
            
            position = node_position.get("position", {})
            timestamp = self._format_timestamp(position)
            emergency_address = (
                f"{position.get('taiwanAddress', {}).get('emergencyAddress', 'x')}"
                f"({position.get('channel', 'x')}/精度{position.get('precisionInMeters', 'x')}m/{timestamp})"
            )
            
        return sender_tag, emergency_address
        
    def _format_timestamp(self, position: Dict) -> str:
        """格式化時間戳"""
        timestamp = position.get("timestamp") or position.get("updateAt")
        if not timestamp:
            return "x"
            
        try:
            if isinstance(timestamp, (int, float)):
                dt = datetime.fromtimestamp(timestamp)
            else:
                dt = datetime.fromisoformat(timestamp)
                
            if dt.tzinfo:
                return dt.strftime("%m-%d %H:%M %Z")
            else:
                return dt.strftime("%m-%d %H:%M")
        except Exception:
            return str(timestamp)
            
    async def _send_emergency_notification(
        self, 
        topic: str, 
        sender_tag: str, 
        emergency_address: Optional[str], 
        message: str
    ) -> None:
        """發送緊急通知"""
        # 限制訊息長度
        if len(message) > 20:
            message = message[:20] + "...(略)"
            
        # 構建通知訊息
        reply = f"🆘 @here 緊急守護通報/{MeshtasticUtil.get_channel_from_topic(topic)}({sender_tag})\n"
        if emergency_address:
            reply += f"{emergency_address}\n"
        reply += f"內容：{message}"
        
        # 發送主要通知
        notify_channel_id = self.config.get("bot", {}).get("emergencyGuardian", {}).get("notifyChannelId")
        response_packet = await self.meshtastic_service.send_packet(
            mesh_packet=self.meshtastic_service.create_text_packet(
                channel_id=notify_channel_id,
                text=reply
            ),
            destination_id="^all",
            want_ack=True
        )
        
        # 發送後續提醒
        if response_packet is not None:
            await asyncio.sleep(random.uniform(0.5, 1))
            await self.meshtastic_service.send_packet(
                mesh_packet=self.meshtastic_service.create_text_packet(
                    channel_id=notify_channel_id,
                    text="@here 提高警覺，注意安全，視情況協助處理",
                    reply_id=getattr(response_packet, "id", None)
                ),
                destination_id="^all",
                want_ack=True
            )
            
        self.logger.info(f"發送緊急守護訊息成功: {reply}")
