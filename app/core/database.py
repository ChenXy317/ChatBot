"""异步数据库引擎与连接会话管理。"""

import logging
from typing import AsyncGenerator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings
from app.models.orm import Base, BotConfig

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.async_db_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库异步会话。"""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """初始化数据库表结构与默认配置。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        result = await session.execute(select(BotConfig).order_by(BotConfig.id))
        configs = list(result.scalars().all())
        if not configs:
            default_config = BotConfig()
            session.add(default_config)
            await session.commit()
            logger.info("已初始化默认机器人配置")
        elif len(configs) > 1:
            keep_id = configs[0].id
            await session.execute(delete(BotConfig).where(BotConfig.id != keep_id))
            await session.commit()
            logger.warning("检测到多条机器人配置，已清理重复记录，保留 ID=%s", keep_id)
