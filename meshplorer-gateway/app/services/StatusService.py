import inspect
import logging
from app.exceptions.BusinessLogicException import BusinessLogicException
from app.utils.ConfigUtil import ConfigUtil


class StatusService:
    """狀態服務，負責檢查系統相關狀態"""
    
    def __init__(self) -> None:
        self.config = ConfigUtil().read_config()
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    async def checker(self) -> None:
        """檢查系統相關狀態"""
        try:
            return None
        except BusinessLogicException as e:
            raise Exception(f"{str(e)}")
        except Exception as e:
            self.logger.error(f"{inspect.currentframe().f_code.co_name}: {str(e)}")
            raise Exception("內部伺服器發生錯誤，請稍後再試")
