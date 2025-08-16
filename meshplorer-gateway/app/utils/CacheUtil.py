import logging
import math
import os
import traceback
from datetime import datetime
from typing import Any, Optional
from app.utils.ConfigUtil import ConfigUtil

logger = logging.getLogger(__name__)


class CacheUtil:
    """快取工具類別，負責處理 JSON 快取檔案的讀寫相關功能"""

    @staticmethod
    def sanitize_value(value) -> Optional[Any]:
        """檢查並處理 NaN 相關數值"""
        if isinstance(value, float) and math.isnan(value):
            return None
        return value

    @staticmethod
    def read_cache_json(filename: str) -> Optional[str]:
        """讀取快取 JSON 檔案內容"""
        try:
            cache_file_path = (
                f"{ConfigUtil().read_config()['cache']['path']}/{filename}.json"
            )
            os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
            if not os.path.exists(cache_file_path):
                # 如果檔案不存在，則回傳 None
                return None
            if (
                os.path.getmtime(cache_file_path)
                < datetime.now().timestamp() - ConfigUtil().read_config()["cache"]["ttl"]
            ):
                # 如果檔案已經過期，則回傳 None
                return None
            with open(cache_file_path, "r") as cache_file:
                content = cache_file.read()
                if not content:
                    # 如果檔案內容為空，則回傳 None
                    return None
                return content
        except Exception as e:
            stacktrace = traceback.format_exc()
            logger.info(stacktrace)
            raise e

    @staticmethod
    def write_cache_json(filename: str, data: str) -> None:
        """寫入快取 JSON 檔案內容"""
        try:
            cache_file_path = (
                f"{ConfigUtil().read_config()['cache']['path']}/{filename}.json"
            )
            os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
            with open(cache_file_path, "w") as cache_file:
                cache_file.write(data)
        except Exception as e:
            stacktrace = traceback.format_exc()
            logger.info(stacktrace)
            raise e
