import aiohttp
import json
import logging
import uuid
import hashlib
from typing import Dict, Any, Optional, List
from app.utils.ConfigUtil import ConfigUtil


class DifyUtil:
    """Dify API 工具類別，負責處理與 Dify 的 API 通信"""

    def __init__(self):
        self.config = ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())
        
        # 從設定檔讀取 Dify 設定
        dify_config = self.config.get("dify", {})
        self.api_base = dify_config.get("api", {}).get("base", "https://api.dify.ai/v1")
        self.api_key = dify_config.get("api", {}).get("key", "")
        
        if not self.api_key or self.api_key == "your-dify-key":
            self.logger.warning("Dify API key 還沒設定，請在 config.yml 中設定正確的 API key")
    
    async def send_chat_message_streaming(
        self,
        query: str,
        user: str = "meshplorer-user",
        conversation_id: str = "",
        inputs: Dict[str, Any] = None,
        files: List[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        發送聊天訊息並取得串流回應
        
        Args:
            query: 使用者查詢內容
            user: 使用者識別碼
            conversation_id: 對話 ID
            inputs: 額外的輸入參數
            files: 檔案列表
            
        Returns:
            完整的回應文字，如果失敗則回傳 None
        """
        if not self.api_key or self.api_key == "your-dify-key":
            self.logger.error("Dify API key 還沒設定，無法發送訊息")
            return None
            
        url = f"{self.api_base}/chat-messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "streaming",
            "conversation_id": conversation_id,
            "user": user
        }
        
        if files:
            payload["files"] = files
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        full_response = ""
                        async for line in response.content:
                            line_str = line.decode('utf-8').strip()
                            if line_str.startswith('data: '):
                                data_str = line_str[6:]  # 移除 'data: ' 前綴
                                if data_str == '[DONE]':
                                    break
                                try:
                                    data = json.loads(data_str)
                                    if 'answer' in data:
                                        full_response += data['answer']
                                except json.JSONDecodeError:
                                    continue
                        
                        self.logger.info(f"成功取得 Dify 串流回應，長度: {len(full_response)}")
                        return full_response
                    else:
                        error_text = await response.text()
                        self.logger.error(
                            f"Dify API 串流請求失敗，狀態碼: {response.status}, "
                            f"錯誤: {error_text}"
                        )
                        return None
                        
        except Exception as e:
            self.logger.error(f"發送 Dify 串流訊息時出錯了: {e}")
            return None
    
    def is_configured(self) -> bool:
        """
        檢查 Dify 是否已經正確設定
        
        Returns:
            如果設定正確回傳 True，否則回傳 False
        """
        return bool(self.api_key and self.api_key != "your-dify-key")
    
    def get_conversation_id(self, user: str) -> str:
        """
        產生或取得對話 ID
        
        Args:
            user: 使用者識別碼
            
        Returns:
            對話 ID (UUID 格式)
        """
        # Dify API 要求 conversation_id 必須是有效的 UUID 格式
        # 為了保持對話上下文，我們根據使用者名稱產生固定的 UUID
        user_hash = hashlib.md5(user.encode()).hexdigest()
        # 將 hash 轉換為 UUID 格式
        uuid_str = f"{user_hash[:8]}-{user_hash[8:12]}-{user_hash[12:16]}-{user_hash[16:20]}-{user_hash[20:32]}"
        return uuid_str
