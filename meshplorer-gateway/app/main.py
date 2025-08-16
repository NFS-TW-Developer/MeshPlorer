import asyncio
import logging
import os
from alembic.config import Config
from alembic import command
from app.configs.Scheduler import start_scheduler, shutdown_scheduler
from app.routers import routers
from app.services.BotService import BotService
from app.utils.ConfigUtil import ConfigUtil
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 設定檔讀取
config = ConfigUtil().read_config()

logger = logging.getLogger(__name__)
logger.setLevel(config.get("log", {}).get("level", "INFO").upper())


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    shutdown_scheduler()


# FastAPI app 設定
app = FastAPI(lifespan=lifespan)

# CORS middleware 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由設定
for router in routers:
    app.include_router(router)


async def start_api():
    logger.info("API 服務正在啟動...")
    process = await asyncio.create_subprocess_exec(
        "gunicorn",
        "-c",
        os.path.join(
            os.getcwd(), "app/gunicorn.conf.py"
        ),  # 讓 Gunicorn 使用 gunicorn.conf.py 設定檔
        "app.main:app",
    )
    await process.communicate()
    logger.info("API 服務已啟動")


async def start_bot():
    logger.info("Bot 正在啟動...")
    task_job = asyncio.create_task(BotService().start())
    logger.info("Bot 已啟動")


async def main():
    logger.info("meshplorer-gateway 正在運行中...")
    # 等待 5 秒以確保服務啟動
    await asyncio.sleep(5)
    logger.info("正在初始化資料庫模型...")
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("正在啟動子服務...")
    api_task = asyncio.create_task(start_api())
    bot_task = asyncio.create_task(start_bot())
    # 並行執行子服務
    await asyncio.gather(asyncio.Future(), api_task, bot_task)
