import asyncio
import logging
import random
from typing import Optional, Dict, Any
import meshtastic
import meshtastic.tcp_interface
from meshtastic import mesh_pb2, portnums_pb2
from app.utils.ConfigUtil import ConfigUtil


class MeshtasticService:
    """Meshtastic 服務，負責封包傳送和裝置相關管理"""
    
    def __init__(self):
        self.config = ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())
        
    async def send_packet(
        self,
        mesh_packet: mesh_pb2.MeshPacket,
        destination_id: Optional[str] = None,
        want_ack: bool = False,
        hop_limit: int = 3,
        retry_count: int = 0,
    ) -> Optional[Any]:
        """傳送封包到 Meshtastic 網路中"""
        await asyncio.sleep(random.uniform(1, 3))  # 隨機延遲1~3秒
        
        try:
            # 隨機從設定檔中取得一個 Meshtastic 介面
            devices = self.config.get("bot", {}).get("devices", [])
            if not devices:
                self.logger.error("沒有可用的 Meshtastic 介面")
                return None
                
            device = random.choice(devices)
            interface = await self._create_interface(device)
            
            if not interface:
                return None
                
            response = interface._sendPacket(
                meshPacket=mesh_packet,
                destinationId=destination_id,
                wantAck=want_ack,
                hopLimit=hop_limit,
            )
            
            self.logger.info(
                f"已傳送封包，device {device.get('name')}: "
                f"channel={getattr(mesh_packet, 'channel')}, "
                f"id={getattr(mesh_packet, 'id')}, "
                f"destination_id={destination_id}"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"傳送封包失敗: {e}")
            if retry_count < 3:
                self.logger.info(f"嘗試重新傳送封包，重試次數: {retry_count + 1}")
                await asyncio.sleep(random.uniform(0.5, 1))
                return await self.send_packet(
                    mesh_packet=mesh_packet,
                    destination_id=destination_id,
                    want_ack=want_ack,
                    hop_limit=hop_limit,
                    retry_count=retry_count + 1,
                )
            return None
        finally:
            await asyncio.sleep(random.uniform(3, 5))  # 確保介面有足夠時間處理封包
            
    async def _create_interface(self, device: Dict[str, Any]):
        """建立 Meshtastic 介面連接"""
        try:
            if device.get("type") == "tcp":
                interface = meshtastic.tcp_interface.TCPInterface(
                    hostname=device.get("host"), 
                    connectNow=False
                )
                interface.myConnect()
                return interface
            else:
                self.logger.error(f"不支援的介面類型: {device.get('type')}")
                return None
        except Exception as e:
            self.logger.error(f"建立介面連接失敗: {e}")
            return None
            
    def create_text_packet(
        self,
        channel_id: int,
        text: str,
        reply_id: Optional[int] = None,
        emoji: bool = False,
        priority: mesh_pb2.MeshPacket.Priority = mesh_pb2.MeshPacket.Priority.BACKGROUND
    ) -> mesh_pb2.MeshPacket:
        """建立文字訊息的封包"""
        return mesh_pb2.MeshPacket(
            channel=channel_id,
            decoded=mesh_pb2.Data(
                payload=text.encode("utf-8"),
                portnum=portnums_pb2.PortNum.TEXT_MESSAGE_APP,
                reply_id=reply_id,
                emoji=1 if emoji else 0,
                bitfield=1 if emoji else 0,
            ),
            priority=priority,
        )
        
    def create_emoji_packet(
        self,
        channel_id: int,
        emoji: str,
        reply_id: Optional[int] = None
    ) -> mesh_pb2.MeshPacket:
        """建立 emoji 封包"""
        return self.create_text_packet(
            channel_id=channel_id,
            text=emoji,
            reply_id=reply_id,
            emoji=True
        )
