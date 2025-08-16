import asyncio
import logging
import os
from app.main import main
from app.utils.ConfigUtil import ConfigUtil
from fastapi.logger import logger as fastapi_logger


def configure_logging():
    log_level = ConfigUtil().read_config().get("log", {}).get("level", "INFO").upper()
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=log_level, format=log_format, handlers=[logging.StreamHandler()]
    )

    # 配置 fastapi_logger 相關設定
    fastapi_logger.setLevel(log_level)
    fastapi_logger.propagate = False  # 防止重複日誌

    # 清除預設的 handlers，避免重複輸出
    if not fastapi_logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(log_format))
        fastapi_logger.addHandler(ch)


def configure_gunicorn_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # 取得 Gunicorn 相關的 logger
    gunicorn_error_logger = logging.getLogger("gunicorn.error")
    gunicorn_access_logger = logging.getLogger("gunicorn.access")

    # 確保 Uvicorn 也使用 Gunicorn 相關的 logger
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers = gunicorn_error_logger.handlers
    uvicorn_access_logger.setLevel(log_level)

    # FastAPI 也使用相同的 logger 設定
    fastapi_logger.handlers = gunicorn_error_logger.handlers
    fastapi_logger.setLevel(log_level)
    fastapi_logger.propagate = False  # 防止重複輸出

    # 確保 Gunicorn handlers 使用統一的格式
    for handler in gunicorn_error_logger.handlers:
        handler.setFormatter(logging.Formatter(log_format))


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
else:
    configure_gunicorn_logging()
