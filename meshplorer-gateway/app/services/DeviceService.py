import asyncio
import inspect
import logging
import random
from typing import Dict, List, Callable, Any, Optional
import meshtastic
import meshtastic.tcp_interface
import meshtastic.serial_interface
from pubsub import pub
from app.utils.ConfigUtil import ConfigUtil


class DeviceService:
    """實體設備服務，負責透過 TCP/Serial 連線接收相關訊息"""
    
    def __init__(self):
        self.config = ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())
        self.message_handlers: List[Callable] = []
        self.devices: List[Dict] = []
        self.interfaces: List[Any] = []
        
    def add_message_handler(self, handler: Callable[[Dict, Any], None]):
        """新增訊息處理器"""
        self.message_handlers.append(handler)
        
    async def start(self):
        """啟動實體設備相關服務"""
        try:
            # 取得所有可用的設備設定
            self.devices = self.config.get("bot", {}).get("devices", [])
            if not self.devices:
                self.logger.warning("沒有找到可用的實體設備相關設定")
                return
                
            self.logger.info(f"找到 {len(self.devices)} 個實體設備設定")
            
            # 為每個設備建立連線相關任務
            tasks = []
            for device in self.devices:
                tasks.append(self._handle_device(device))
                
            # 併發處理所有設備連線
            await asyncio.gather(*tasks)
            
        except Exception as e:
            self.logger.error(f"啟動實體設備服務時發生錯誤: {e}")
            
    async def _handle_device(self, device: Dict):
        """處理單一實體設備連線"""
        device_name = device.get("name", "unknown")
        device_type = device.get("type", "tcp")
        
        self.logger.info(f"正在連線到設備: {device_name} (連線類型: {device_type})")
        
        while True:
            try:
                # 建立設備介面連接
                interface = await self._create_interface(device)
                if not interface:
                    self.logger.error(f"無法建立設備 {device_name} 的介面連接")
                    await asyncio.sleep(30)  # 等待 30 秒後重試
                    continue
                    
                self.interfaces.append(interface)
                self.logger.info(f"成功連線到設備: {device_name}")
                
                # 設定訊息接收的回調函數
                await self._setup_message_receiver(interface, device)
                
                # 保持連線狀態
                while True:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                self.logger.error(f"設備 {device_name} 連線時發生錯誤: {e}")
                await asyncio.sleep(30)  # 等待 30 秒後重試
                continue
                
    async def _create_interface(self, device: Dict) -> Optional[Any]:
        """建立設備介面連接"""
        try:
            device_type = device.get("type", "tcp")
            
            if device_type == "tcp":
                hostname = device.get("host")
                if not hostname:
                    self.logger.error("TCP 設備缺少 host 相關設定")
                    return None
                    
                interface = meshtastic.tcp_interface.TCPInterface(
                    hostname=hostname,
                    noProto=False
                )
                return interface
                
            elif device_type == "serial":
                port = device.get("port")
                if not port:
                    self.logger.error("Serial 設備缺少 port 設定")
                    return None
                    
                interface = meshtastic.serial_interface.SerialInterface(
                    devPath=port,
                    noProto=False
                )
                return interface
                
            else:
                self.logger.error(f"不支援的設備類型: {device_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"建立設備介面失敗: {e}")
            return None
            
    async def _setup_message_receiver(self, interface: Any, device: Dict):
        """設定訊息接收器"""
        device_name = device.get("name", "unknown")
        
        # 包裝回調函數以支援 async
        def _on_receive_wrapper(packet: Dict, interface_instance: Any):
            """包裝訊息接收回調"""
            try:
                # 使用 asyncio.create_task 來處理 async 回調
                asyncio.create_task(self._on_device_message(packet, interface_instance, device))
            except Exception as e:
                self.logger.error(f"處理設備 {device_name} 訊息時發生錯誤: {e}")
                
        # 註冊 pubsub 事件
        pub.subscribe(_on_receive_wrapper, "meshtastic.receive")
        
        # 可選：註冊連線斷開事件
        def _on_disconnect_wrapper(interface_instance: Any):
            """處理連線斷開"""
            self.logger.warning(f"設備 {device_name} 連線已斷開")
            
        pub.subscribe(_on_disconnect_wrapper, "meshtastic.connection.lost")
        
        self.logger.info(f"已設定設備 {device_name} 的訊息接收器")
        
    async def _on_device_message(self, packet: Dict, interface: Any, device: Dict):
        """處理來自實體設備的訊息"""
        try:
            device_name = device.get("name", "unknown")
            
            # 檢查封包格式
            if not isinstance(packet, dict):
                self.logger.debug(f"設備 {device_name} 收到無效封包格式")
                return
                
            # 記錄收到的訊息
            portnum = packet.get("decoded", {}).get("portnum")
            self.logger.info(f"設備 {device_name} 收到訊息，portnum: {portnum}")
            
            # 呼叫所有註冊的訊息處理器
            for handler in self.message_handlers:
                try:
                    await handler(packet, interface)
                except Exception as e:
                    self.logger.error(f"訊息處理器執行失敗: {e}")
                    
        except Exception as e:
            self.logger.error(f"處理設備訊息時發生錯誤: {e}")
            
    async def send_packet(
        self,
        mesh_packet: Any,
        destination_id: Optional[str] = None,
        want_ack: bool = False,
        hop_limit: int = 3,
        device_name: Optional[str] = None
    ) -> Optional[Any]:
        """透過實體設備發送封包"""
        try:
            # 選擇要使用的設備
            target_interface = None
            
            if device_name:
                # 如果指定了設備名稱，使用該設備
                for i, device in enumerate(self.devices):
                    if device.get("name") == device_name and i < len(self.interfaces):
                        target_interface = self.interfaces[i]
                        break
            else:
                # 隨機選擇一個可用的設備
                if self.interfaces:
                    target_interface = random.choice(self.interfaces)
                    
            if not target_interface:
                self.logger.error("沒有可用的設備介面")
                return None
                
            # 發送封包
            response = target_interface._sendPacket(
                meshPacket=mesh_packet,
                destinationId=destination_id,
                wantAck=want_ack,
                hopLimit=hop_limit,
            )
            
            self.logger.info(
                f"已透過實體設備發送封包: "
                f"channel={getattr(mesh_packet, 'channel')}, "
                f"id={getattr(mesh_packet, 'id')}, "
                f"destination_id={destination_id}"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"透過實體設備發送封包失敗: {e}")
            return None
            
    async def stop(self):
        """停止實體設備服務"""
        try:
            # 關閉所有設備連線
            for interface in self.interfaces:
                try:
                    if hasattr(interface, 'close'):
                        interface.close()
                    elif hasattr(interface, 'myDisconnect'):
                        interface.myDisconnect()
                except Exception as e:
                    self.logger.error(f"關閉設備連線時發生錯誤: {e}")
                    
            self.interfaces.clear()
            self.logger.info("實體設備服務已停止")
            
        except Exception as e:
            self.logger.error(f"停止實體設備服務時發生錯誤: {e}")
