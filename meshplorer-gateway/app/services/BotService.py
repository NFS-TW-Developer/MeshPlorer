import asyncio
import base64
import inspect
import json
import logging
import time
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2
from google.protobuf.json_format import MessageToJson

from app.utils.ConfigUtil import ConfigUtil
from app.utils.MeshtasticUtil import MeshtasticUtil
from app.services.MqttService import MqttService
from app.services.MessageHandlerService import MessageHandlerService
from app.services.EmergencyGuardianService import EmergencyGuardianService
from app.services.MeshtasticService import MeshtasticService


class BotService:
    """機器人主服務，負責協調各個子服務的運作"""

    def __init__(self) -> None:
        self.config = ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())

        # 初始化各個子服務
        self.meshtastic_service = MeshtasticService()
        self.mqtt_service = MqttService()
        self.message_handler = MessageHandlerService(self.meshtastic_service)
        self.emergency_service = EmergencyGuardianService(self.meshtastic_service)

        # 註冊 MQTT 訊息處理器
        self.mqtt_service.add_message_handler(self.on_mqtt_message)

        # 設定事件迴圈
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

    async def start(self):
        """啟動機器人服務"""
        self.logger.info("啟動 BotService，開始處理 MQTT 訊息...")
        await self.mqtt_service.start()

    async def on_mqtt_message(self, client, userdata, message):
        """處理 MQTT 訊息的主要進入點"""
        try:
            topic: str = message.topic.value

            # 過濾無效的主題
            if not self._is_valid_topic(topic):
                return

            # 處理 Meshtastic 封包
            if "/2/e/" in topic:
                await self._handle_meshtastic_packet(topic, message.payload)

        except Exception as e:
            self.logger.error(f"處理 MQTT 訊息時發生錯誤: {e}")

    def _is_valid_topic(self, topic: str) -> bool:
        """檢查主題是否有效"""
        if "#" in topic:
            self.logger.error(f"忽略包含 # 的無效主題: {topic}")
            return False
        elif "/2/stat/" in topic:
            # Meshtastic Firmware 2.4.1.394e0e1 版本開始棄用
            return False
        return True

    async def _handle_meshtastic_packet(self, topic: str, payload: bytes):
        """處理 Meshtastic 封包"""
        try:
            # 解析服務封包
            se = mqtt_pb2.ServiceEnvelope()
            se.ParseFromString(payload)
            mp = se.packet

            # 檢查是否為需要忽略的 id
            if self._is_ignored_id(mp):
                return

            # 處理加密的封包
            if mp.HasField("encrypted") and not mp.HasField("decoded"):
                mp = self._decode_encrypted_packet(topic, mp)
                if mp is None:
                    return

            # 只處理文字類型的訊息
            if mp.decoded.portnum != portnums_pb2.TEXT_MESSAGE_APP:
                return

            # 檢查訊息的時效性
            if not self._is_message_timely(mp):
                return

            # 將訊息路由到適當的處理器
            await self._route_message(mp, topic)

        except Exception as e:
            self.logger.error(f"處理 Meshtastic 封包時發生錯誤: {e}")

    def _decode_encrypted_packet(
        self, topic: str, mp: mesh_pb2.MeshPacket
    ) -> Optional[mesh_pb2.MeshPacket]:
        """解密加密的封包"""
        try:
            # 取得解密金鑰
            key = self._get_decryption_key(topic)
            if key is None:
                return None

            # 建立解密器
            nonce = self._create_nonce(mp)
            cipher = Cipher(
                algorithms.AES(base64.b64decode(key.encode("ascii"))),
                modes.CTR(nonce),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()
            decrypted_bytes = decryptor.update(mp.encrypted) + decryptor.finalize()

            # 解析解密後的資料內容
            data = mesh_pb2.Data()
            data.ParseFromString(decrypted_bytes)
            mp.decoded.CopyFrom(data)

            return mp

        except Exception as e:
            self.logger.debug(f"解密失敗: {e}")
            return None

    def _get_decryption_key(self, topic: str) -> Optional[str]:
        """取得解密用的金鑰"""
        # 解析頻道名稱
        channel = topic.split("/")[-2]

        # PKI 頻道不需要進行解密
        if channel == "PKI":
            return None

        # 取得工作頻道的金鑰
        key_list = self.config.get("bot", {}).get("workChannells", [])

        # 新增緊急守護頻道的金鑰
        emergency_guardian = self.config.get("bot", {}).get("emergencyGuardian", {})
        if emergency_guardian:
            key_list.append(
                {
                    "name": emergency_guardian.get("channelName", "emergencyGuardian"),
                    "key": emergency_guardian.get("channelKey", ""),
                }
            )

        # 尋找對應的金鑰
        for item in key_list:
            if item["name"] == channel:
                return item["key"]
        return None

    def _create_nonce(self, mp: mesh_pb2.MeshPacket) -> bytes:
        """建立解密用的隨機數"""
        nonce_packet_id = mp.id.to_bytes(8, "little")
        nonce_from_node = getattr(mp, "from").to_bytes(8, "little")
        return nonce_packet_id + nonce_from_node

    def _is_ignored_id(self, mp: mesh_pb2.MeshPacket) -> bool:
        """檢查是否為忽略的 id"""
        try:
            # 取得來源節點的 id
            id = getattr(mp, "from")

            # 取得忽略清單
            ignore_list = self.config.get("bot", {}).get("ignoreId", [])

            # 檢查是否在忽略清單中
            if str(id) in ignore_list:
                self.logger.debug(
                    f"忽略來自 id {id} 的封包: "
                    f"{mp.decoded.payload.decode('utf-8', errors='ignore')}"
                )
                return True

            return False

        except Exception as e:
            self.logger.error(f"檢查 hexid 時發生錯誤: {e}")
            return False

    def _is_message_timely(self, mp: mesh_pb2.MeshPacket) -> bool:
        """檢查訊息是否在時效內"""
        if hasattr(mp, "rx_time") and mp.rx_time < time.time() - 30:
            self.logger.info(
                f"忽略過期封包，rx_time: "
                f"{datetime.fromtimestamp(mp.rx_time, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}/"
                f"now: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}，"
                f"內容: {mp.decoded.payload.decode('utf-8', errors='ignore')}"
            )
            return False
        return True

    async def _route_message(self, mp: mesh_pb2.MeshPacket, topic: str):
        """將訊息路由到適當的處理器"""
        channel_name = MeshtasticUtil.get_channel_from_topic(topic)

        # 檢查是否為緊急守護頻道
        emergency_channel = (
            self.config.get("bot", {}).get("emergencyGuardian", {}).get("channelName")
        )
        if channel_name == emergency_channel:
            await self.emergency_service.handle_emergency_message(mp, topic)
            return

        # 檢查是否為工作頻道
        work_channel_id = self._get_work_channel_id(channel_name)
        if work_channel_id:
            # 非阻塞處理訊息
            asyncio.create_task(
                self.message_handler.handle_channel_message(mp, work_channel_id)
            )
            return

        # 未知頻道
        self.logger.error(
            f"頻道 {channel_name} 不在允許的頻道清單中，忽略此訊息: "
            f"{mp.decoded.payload.decode('utf-8', errors='ignore')}"
        )

    def _get_work_channel_id(self, channel_name: str) -> Optional[int]:
        """取得工作頻道 ID"""
        work_channels = self.config.get("bot", {}).get("workChannells", [])
        for item in work_channels:
            if item["name"] == channel_name:
                return item["id"]
        return None
