"""Web 管理控制台 REST API 路由。"""

import time
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db_session
from app.gateway.onebot_ws import gateway
from app.models.orm import BotConfig, ChatMessage, SystemLog, WhitelistUser
from app.schemas.common import (
    BotConfigRead,
    BotConfigUpdate,
    ChatMessageRead,
    SystemLogRead,
    TestConnectionRequest,
    TestConnectionResponse,
    WhitelistUserCreate,
    WhitelistUserRead,
    WhitelistUserUpdate,
)

router = APIRouter(prefix="/api")


# ── 配置管理 ──

@router.get("/config", response_model=BotConfigRead)
async def get_config(db: AsyncSession = Depends(get_db_session)):
    """获取当前机器人配置。"""
    res = await db.execute(select(BotConfig).limit(1))
    cfg = res.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="未找到配置")
    return cfg


@router.put("/config", response_model=BotConfigRead)
async def update_config(payload: BotConfigUpdate, db: AsyncSession = Depends(get_db_session)):
    """更新机器人全局配置。"""
    res = await db.execute(select(BotConfig).limit(1))
    cfg = res.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="未找到配置")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cfg, k, v)

    cfg.updated_at = datetime.now()
    await db.commit()
    await db.refresh(cfg)
    return cfg


@router.post("/config/test", response_model=TestConnectionResponse)
async def test_llm_connection(payload: TestConnectionRequest):
    """测试模型接口连通性与响应速度。"""
    start_time = time.time()
    try:
        client = AsyncOpenAI(
            api_key=payload.api_key or "sk-no-auth",
            base_url=payload.api_base.rstrip("/"),
            timeout=15.0,
        )
        resp = await client.chat.completions.create(
            model=payload.model,
            messages=[{"role": "user", "content": "你好，这是一条连接测试消息，请回复两个字：收到"}],
            max_tokens=200,
        )
        latency = (time.time() - start_time) * 1000
        reply = resp.choices[0].message.content or ""
        return TestConnectionResponse(
            success=True,
            latency_ms=round(latency, 2),
            reply=reply.strip(),
        )
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return TestConnectionResponse(
            success=False,
            latency_ms=round(latency, 2),
            reply="",
            error=str(e),
        )


# ── 白名单管理 ──

@router.get("/whitelist", response_model=List[WhitelistUserRead])
async def list_whitelist(db: AsyncSession = Depends(get_db_session)):
    """获取所有白名单好友列表。"""
    res = await db.execute(select(WhitelistUser).order_by(WhitelistUser.id.desc()))
    return res.scalars().all()


@router.post("/whitelist", response_model=WhitelistUserRead)
async def add_whitelist_user(payload: WhitelistUserCreate, db: AsyncSession = Depends(get_db_session)):
    """添加好友至接管白名单。"""
    res = await db.execute(select(WhitelistUser).where(WhitelistUser.user_id == payload.user_id))
    existing = res.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="该 QQ 号已在白名单中")

    user = WhitelistUser(**payload.model_dump())
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/whitelist/{user_id}", response_model=WhitelistUserRead)
async def update_whitelist_user(
    user_id: int, payload: WhitelistUserUpdate, db: AsyncSession = Depends(get_db_session)
):
    """修改白名单用户配置或开关状态。"""
    res = await db.execute(select(WhitelistUser).where(WhitelistUser.user_id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="未找到该白名单用户")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/whitelist/{user_id}")
async def delete_whitelist_user(user_id: int, db: AsyncSession = Depends(get_db_session)):
    """从白名单中移除好友。"""
    res = await db.execute(select(WhitelistUser).where(WhitelistUser.user_id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="未找到该白名单用户")

    await db.delete(user)
    await db.commit()
    return {"success": True}


# ── 历史消息与状态 ──

@router.get("/messages/{user_id}", response_model=List[ChatMessageRead])
async def get_user_messages(user_id: int, limit: int = 50, db: AsyncSession = Depends(get_db_session)):
    """获取指定好友的历史聊天记录。"""
    res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    records = list(reversed(res.scalars().all()))
    return records


@router.get("/logs", response_model=List[SystemLogRead])
async def get_system_logs(limit: int = 50, db: AsyncSession = Depends(get_db_session)):
    """获取系统最新运行日志。"""
    res = await db.execute(
        select(SystemLog).order_by(SystemLog.id.desc()).limit(limit)
    )
    return list(reversed(res.scalars().all()))


@router.get("/status")
async def get_system_status():
    """获取当前服务与 NapCat 连接状态。"""
    return {
        "napcat_connected": gateway.is_connected,
        "active_debouncers": len(gateway.debouncer._sessions) if gateway.debouncer else 0,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
