from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from app.utils.ConfigUtil import ConfigUtil
import logging

# 讀取設定檔
config_data = ConfigUtil().read_config()
db_config = config_data["postgres"]

# 同步資料庫 URL
DATABASE_URL_SYNC = (
    f"postgresql+psycopg2://{db_config['username']}:{db_config['password']}@"
    f"{db_config['host']}:{db_config['port']}/{db_config['database']}"
)

# 非同步資料庫 URL
DATABASE_URL_ASYNC = (
    f"postgresql+asyncpg://{db_config['username']}:{db_config['password']}@"
    f"{db_config['host']}:{db_config['port']}/{db_config['database']}"
)

# 建立同步引擎
Engine = create_engine(DATABASE_URL_SYNC, pool_pre_ping=True)

# 建立非同步引擎 (future=True 在 SQLAlchemy 2.0+ 已是預設)
EngineAsync = create_async_engine(DATABASE_URL_ASYNC, pool_pre_ping=True)

# 同步 Session Maker
SessionLocal = sessionmaker(Engine, expire_on_commit=False)

# 非同步 Session Maker (官方推薦設定 expire_on_commit=False)
SessionLocalAsync = async_sessionmaker(EngineAsync, expire_on_commit=False)


# 同步資料庫依賴注入函數
def get_db_connection():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logging.exception("同步資料庫操作失敗，已 rollback: %s", e)
        raise
    finally:
        db.close()


# 非同步資料庫依賴注入函數（官方推薦寫法）
async def get_db_connection_async() -> AsyncSession:
    async with SessionLocalAsync() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logging.exception("非同步資料庫操作失敗，已 rollback: %s", e)
            raise
        finally:
            await session.close()
