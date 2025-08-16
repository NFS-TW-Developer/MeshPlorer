import asyncio
import inspect
import logging
from typing import Dict, List, Callable, Any
import aiomqtt
from app.utils.ConfigUtil import ConfigUtil


class MqttService:
    """MQTT 服務，負責處理 MQTT 連線和訊息接收相關功能"""
    
    def __init__(self):
        self.config = ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())
        self.message_handlers: List[Callable] = []
        
    def add_message_handler(self, handler: Callable[[aiomqtt.Client, Any, aiomqtt.Message], None]):
        """新增訊息處理器"""
        self.message_handlers.append(handler)
        
    async def start(self):
        """啟動 MQTT 服務"""
        tasks = []
        for mqtt_client in self.config["mqtt"]["client"]:
            tasks.append(self._handle_client(mqtt_client))
        await asyncio.gather(*tasks)
        
    async def _handle_client(self, client_config: Dict):
        """處理單一 MQTT 客戶端的設定"""
        tasks = []
        for host in client_config["hosts"]:
            tasks.append(self._subscribe_to_host(client_config, host))
        await asyncio.gather(*tasks)
        
    async def _subscribe_to_host(self, client_config: Dict, host: str):
        """訂閱到指定的主機端"""
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=host,
                    port=client_config["port"],
                    identifier=client_config["identifier"],
                    username=client_config["username"],
                    password=client_config["password"],
                ) as client:
                    # 訂閱多個主題
                    for topic in client_config["topics"]:
                        await client.subscribe(topic)
                    self.logger.info(f"已訂閱 {host} 的主題: {client_config['topics']}")
                    
                    async for message in client.messages:
                        await self._on_mqtt_message(client, None, message)
                        
            except Exception as e:
                if client_config.get("showErrorLog", True):
                    self.logger.error(f"{inspect.currentframe().f_code.co_name}: {e}")
                    self.logger.error(f"{host} 訂閱服務發生錯誤，正在進行重試...")
                await asyncio.sleep(client_config.get("retryTime", 5))
                continue
                
    async def _on_mqtt_message(self, client: aiomqtt.Client, userdata: Any, message: aiomqtt.Message):
        """處理 MQTT 訊息"""
        try:
            # 呼叫所有註冊的訊息處理器
            for handler in self.message_handlers:
                try:
                    await handler(client, userdata, message)
                except Exception as e:
                    self.logger.error(f"訊息處理器執行失敗: {e}")
        except Exception as e:
            self.logger.error(f"處理 MQTT 訊息時發生錯誤: {e}")
