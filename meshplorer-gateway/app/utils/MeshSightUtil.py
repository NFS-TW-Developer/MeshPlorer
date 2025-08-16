import aiohttp
import asyncio
import inspect
import logging
from app.exceptions.BusinessLogicException import BusinessLogicException
from app.utils.ConfigUtil import ConfigUtil
from typing import Optional


class MeshSightUtil:
    """MeshSight 工具類別，負責與 MeshSight API 進行互動"""

    def __init__(
        self,
        config: dict = None,
    ) -> None:
        self.config = ConfigUtil().read_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(self.config.get("log", {}).get("level", "INFO").upper())

    async def get_node_info(self, node_id: int) -> Optional[dict]:
        """透過節點 ID 取得節點資訊"""
        try:
            self.logger.info(f"取得節點資訊，節點 ID: {node_id}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config['meshsight']['api']['url']}/v1/node/info/{node_id}",
                ) as response:
                    if response.status != 200:
                        raise BusinessLogicException(
                            f"無法取得節點資訊，狀態碼: {response.status}\n{await response.text()}"
                        )
                    result = await response.json()
                    if result.get("status") != "success":
                        raise BusinessLogicException(
                            f"無法取得節點資訊，錯誤訊息: {result.get('message', '未知錯誤')}"
                        )
                    result_data = result.get("data")
                    if not result_data:
                        raise BusinessLogicException("節點資訊為空")
                    return result_data
        except BusinessLogicException as e:
            self.logger.error(f"{inspect.currentframe().f_code.co_name}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"{inspect.currentframe().f_code.co_name}: {str(e)}")
            return None

    async def get_node_position(self, node_id: int) -> Optional[dict]:
        """透過節點 ID 取得節點位置資訊"""
        try:
            self.logger.info(f"取得節點位置，節點 ID: {node_id}")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config['meshsight']['api']['url']}/v1/node/position/{node_id}",
                ) as response:
                    if response.status != 200:
                        raise BusinessLogicException(
                            f"無法取得節點位置，狀態碼: {response.status}\n{await response.text()}"
                        )
                    result = await response.json()
                    if result.get("status") != "success":
                        raise BusinessLogicException(
                            f"無法取得節點位置，錯誤訊息: {result.get('message', '未知錯誤')}"
                        )
                    result_data = result.get("data")
                    if not result_data:
                        raise BusinessLogicException("節點位置資訊為空")
                    return result_data
        except BusinessLogicException as e:
            self.logger.error(f"{inspect.currentframe().f_code.co_name}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"{inspect.currentframe().f_code.co_name}: {str(e)}")
            return None
