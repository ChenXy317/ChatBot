"""异步数据库引擎与连接会话管理。"""

import logging
from typing import AsyncGenerator
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings
from app.engine.prompt_builder import (
    DEFAULT_OUTPUT_PROMPT,
    DEFAULT_ROLE_PROMPT,
    LEGACY_DEFAULT_SYSTEM_PROMPT,
)
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
        await _upgrade_bot_config_schema(conn)

    async with async_session_factory() as session:
        result = await session.execute(select(BotConfig).order_by(BotConfig.id))
        configs = list(result.scalars().all())
        if not configs:
            legacy_columns = await session.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() "
                    "AND table_name = 'bot_config' "
                    "AND column_name = 'system_prompt'"
                )
            )
            has_legacy_system_prompt = bool(legacy_columns.scalar())
            if has_legacy_system_prompt:
                # 旧版表要求 system_prompt 非空。先插入兼容值，再走统一的
                # 旧字段迁移，避免新版本首次启动被遗留约束阻塞。
                legacy_prompt = DEFAULT_ROLE_PROMPT + "\n\n" + DEFAULT_OUTPUT_PROMPT
                await session.execute(
                    text(
                        "INSERT INTO bot_config "
                        "(api_base, api_key, model, role_prompt, output_prompt, "
                        "system_prompt, temperature, top_p, max_tokens, "
                        "debounce_delay, typing_speed, is_enabled, updated_at) "
                        "VALUES (:api_base, '', :model, :role_prompt, :output_prompt, "
                        ":system_prompt, 0.8, 0.9, 2048, 1.5, 0.15, 1, NOW())"
                    ),
                    {
                        "api_base": "https://api.deepseek.com/v1",
                        "model": "deepseek-chat",
                        "role_prompt": DEFAULT_ROLE_PROMPT,
                        "output_prompt": DEFAULT_OUTPUT_PROMPT,
                        "system_prompt": legacy_prompt,
                    },
                )
                await session.commit()
                logger.info("已按旧版表结构初始化默认机器人配置")
                result = await session.execute(select(BotConfig).order_by(BotConfig.id))
                configs = list(result.scalars().all())
            else:
                default_config = BotConfig()
                session.add(default_config)
                await session.commit()
                logger.info("已初始化默认机器人配置")
        elif len(configs) > 1:
            keep_id = configs[0].id
            await session.execute(delete(BotConfig).where(BotConfig.id != keep_id))
            await session.commit()
            logger.warning("检测到多条机器人配置，已清理重复记录，保留 ID=%s", keep_id)


async def _upgrade_bot_config_schema(conn) -> None:
    """兼容旧库：把 system_prompt 拆成 role_prompt 与 output_prompt。"""
    columns = await conn.run_sync(
        lambda sync_conn: {column["name"] for column in inspect(sync_conn).get_columns("bot_config")}
    )
    if "role_prompt" not in columns:
        await conn.execute(text("ALTER TABLE bot_config ADD COLUMN role_prompt TEXT NULL"))
    if "output_prompt" not in columns:
        await conn.execute(text("ALTER TABLE bot_config ADD COLUMN output_prompt TEXT NULL"))
    if "system_prompt" in columns:
        legacy_result = await conn.execute(
            text("SELECT id, system_prompt, role_prompt, output_prompt FROM bot_config")
        )
        for row in legacy_result.mappings():
            system_prompt = (row["system_prompt"] or "").strip()
            role_prompt = (row["role_prompt"] or "").strip()
            output_prompt = (row["output_prompt"] or "").strip()
            if system_prompt and not role_prompt and not output_prompt:
                if system_prompt == LEGACY_DEFAULT_SYSTEM_PROMPT.strip():
                    role_prompt = DEFAULT_ROLE_PROMPT
                    output_prompt = DEFAULT_OUTPUT_PROMPT
                else:
                    role_prompt = system_prompt
            await conn.execute(
                text(
                    "UPDATE bot_config SET role_prompt = :role_prompt, "
                    "output_prompt = :output_prompt WHERE id = :id"
                ),
                {
                    "id": row["id"],
                    "role_prompt": role_prompt,
                    "output_prompt": output_prompt,
                },
            )
    await conn.execute(
        text(
            "UPDATE bot_config SET "
            "role_prompt = COALESCE(NULLIF(role_prompt, ''), :role_prompt), "
            "output_prompt = COALESCE(NULLIF(output_prompt, ''), :output_prompt)"
        ),
        {
            "role_prompt": DEFAULT_ROLE_PROMPT,
            "output_prompt": DEFAULT_OUTPUT_PROMPT,
        },
    )
    await conn.execute(
        text(
            "UPDATE bot_config SET role_prompt = :role_prompt "
            "WHERE TRIM(role_prompt) LIKE :legacy_role_prefix"
        ),
        {
            "role_prompt": DEFAULT_ROLE_PROMPT,
            "legacy_role_prefix": f"{DEFAULT_ROLE_PROMPT}%【行为规范】%",
        },
    )
