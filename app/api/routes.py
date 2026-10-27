"""Web 管理控制台 REST API 路由。"""

import time
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db_session
from app.engine.account_manager import account_manager
from app.gateway.onebot_ws import gateway
from app.models.orm import BotConfig, ChatMessage, SystemLog, WhitelistUser
from app.schemas.common import (
    AccountItem,
    AccountLaunchRequest,
    AccountListResponse,
    AccountSetDefaultRequest,
    AccountSwitchRequest,
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
        raw_reply = resp.choices[0].message.content or ""
        from app.engine.think_stripper import ThinkStripper
        reply = ThinkStripper().strip(raw_reply)
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


# ── 账号管理与协议端控制 ──

@router.get("/accounts", response_model=AccountListResponse)
async def list_accounts():
    """获取所有已记录的 QQ 账号及当前状态。"""
    return account_manager.list_accounts()


@router.post("/accounts/switch")
async def switch_account(payload: AccountSwitchRequest):
    """切换至指定账号并可选自动拉起 NapCat。"""
    qq = payload.qq.strip()
    if not qq:
        raise HTTPException(status_code=400, detail="QQ 账号不能为空")

    account_manager.set_default_account(qq)
    account_manager.ensure_ws_config(qq)

    if payload.auto_start:
        result = account_manager.launch_napcat(qq=qq)
        return result
    return {"success": True, "message": f"已将账号 {qq} 设为下一次启动账号"}


@router.post("/accounts/set-default")
async def set_default_account(payload: AccountSetDefaultRequest):
    """将指定账号设为默认启动账号。"""
    qq = payload.qq.strip()
    if not qq:
        raise HTTPException(status_code=400, detail="QQ 账号不能为空")
    account_manager.set_default_account(qq)
    account_manager.ensure_ws_config(qq)
    return {"success": True, "message": f"已设为默认账号: {qq}"}


@router.post("/accounts/launch")
async def launch_account(payload: AccountLaunchRequest):
    """启动或重启 NapCat 进程（支持指定 QQ 或扫码模式）。"""
    return account_manager.launch_napcat(qq=payload.qq, qr_mode=payload.qr_mode)


@router.post("/accounts/stop")
async def stop_napcat():
    """停止运行中的 NapCat/QQ 进程。"""
    ok = account_manager.stop_napcat()
    return {"success": ok, "message": "已发送停止进程指令"}


@router.delete("/accounts/{qq}")
async def delete_account(qq: str):
    """删除本地指定账号的配置文件。"""
    clean_qq = qq.strip()
    if gateway.is_connected and gateway.current_qq == clean_qq:
        raise HTTPException(status_code=400, detail="当前账号正在连接中，请先停止运行或切换账号后再删除")
    ok = account_manager.delete_account(clean_qq)
    return {"success": ok}


@router.get("/accounts/qrcode")
async def get_qrcode():
    """获取扫码登录二维码图片。"""
    qr_path = account_manager.get_qrcode_path()
    if not qr_path:
        raise HTTPException(status_code=404, detail="未检测到有效二维码")
    return FileResponse(qr_path, media_type="image/png")


# ── 系统状态 ──

@router.get("/status")
async def get_system_status():
    """获取当前服务与 NapCat 连接状态。"""
    return {
        "napcat_connected": gateway.is_connected,
        "current_qq": gateway.current_qq,
        "current_nickname": gateway.current_nickname,
        "is_process_running": account_manager.is_process_running(),
        "default_account": account_manager.get_default_account(),
        "active_debouncers": len(gateway.debouncer._sessions) if gateway.debouncer else 0,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
