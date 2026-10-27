"""Web 管理控制台 REST API 路由。"""

import asyncio
import os
import subprocess
import time
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db_session
from app.engine.account_manager import ROOT_DIR, account_manager
from app.gateway.onebot_ws import gateway
from app.models.orm import BotConfig, ChatMessage, SystemLog, WhitelistUser
from app.schemas.common import (
    AccountItem,
    AccountLaunchRequest,
    AccountListResponse,
    AccountLoginStatus,
    AccountQuickLoginRequest,
    AccountSetDefaultRequest,
    AccountSwitchRequest,
    BotConfigRead,
    ChatMessageUpdate,
    DeferredBotConfigUpdate,
    ChatMessageRead,
    MessageOwnerRead,
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
    values = {
        column.name: getattr(cfg, column.name)
        for column in BotConfig.__table__.columns
        if column.name != "api_key"
    }
    values["api_key"] = ""
    values["api_key_set"] = bool(cfg.api_key)
    return BotConfigRead(
        **values,
    )


@router.put("/config", response_model=BotConfigRead)
async def update_config(payload: DeferredBotConfigUpdate, db: AsyncSession = Depends(get_db_session)):
    """更新机器人全局配置。"""
    res = await db.execute(select(BotConfig).limit(1))
    cfg = res.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="未找到配置")

    changes = payload.model_dump(exclude_unset=True)
    if not changes.get("api_key"):
        changes.pop("api_key", None)
    for k, v in changes.items():
        setattr(cfg, k, v)

    cfg.updated_at = datetime.now()
    await db.commit()
    await db.refresh(cfg)
    values = {
        column.name: getattr(cfg, column.name)
        for column in BotConfig.__table__.columns
        if column.name != "api_key"
    }
    values["api_key"] = ""
    values["api_key_set"] = bool(cfg.api_key)
    return BotConfigRead(**values)


class SystemShutdownRequest(BaseModel):
    """本地控制台关闭系统请求。"""
    restart: bool = False


class MessageSendRequest(BaseModel):
    """本地控制台向指定 QQ 发送测试消息。"""
    user_id: int = Field(..., ge=10000)
    message: str = Field(..., min_length=1, max_length=500)


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

@router.get("/message-users", response_model=List[MessageOwnerRead])
async def list_message_users(db: AsyncSession = Depends(get_db_session)):
    """列出数据库中所有拥有聊天记录的好友，不受白名单状态限制。"""
    res = await db.execute(
        select(
            ChatMessage.user_id,
            func.count(ChatMessage.id).label("message_count"),
            func.max(ChatMessage.created_at).label("last_message_at"),
        )
        .group_by(ChatMessage.user_id)
        .order_by(func.max(ChatMessage.created_at).desc())
    )
    return [dict(row._mapping) for row in res.all()]


@router.get("/messages/{user_id}", response_model=List[ChatMessageRead])
async def get_user_messages(user_id: int, db: AsyncSession = Depends(get_db_session)):
    """获取指定好友的全部历史聊天记录。"""
    res = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.id.asc())
    )
    return res.scalars().all()


@router.patch("/messages/{message_id}", response_model=ChatMessageRead)
async def update_chat_message(
    message_id: int,
    payload: ChatMessageUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    """修改指定历史消息的文字与图片。"""
    res = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    message = res.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="未找到该消息")

    changes = payload.model_dump(exclude_unset=True)
    if "content" in changes:
        changes["content"] = changes["content"].strip()
        if not changes["content"]:
            raise HTTPException(status_code=400, detail="消息内容不能为空")
    if "image_urls" in changes:
        changes["image_urls"] = changes["image_urls"] or None
    for key, value in changes.items():
        setattr(message, key, value)

    await db.commit()
    await db.refresh(message)
    return message


@router.delete("/messages/{message_id}")
async def delete_chat_message(message_id: int, db: AsyncSession = Depends(get_db_session)):
    """删除指定历史消息。"""
    res = await db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
    message = res.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="未找到该消息")
    await db.delete(message)
    await db.commit()
    return {"success": True}


@router.delete("/messages/user/{user_id}")
async def clear_user_messages(user_id: int, db: AsyncSession = Depends(get_db_session)):
    """清空指定好友的全部历史消息。"""
    result = await db.execute(delete(ChatMessage).where(ChatMessage.user_id == user_id))
    await db.commit()
    return {"success": True, "deleted": result.rowcount or 0}


@router.get("/logs", response_model=List[SystemLogRead])
async def get_system_logs(limit: int = 50, db: AsyncSession = Depends(get_db_session)):
    """获取系统最新运行日志。"""
    res = await db.execute(
        select(SystemLog).order_by(SystemLog.id.desc()).limit(limit)
    )
    return list(reversed(res.scalars().all()))


# ── 账号管理与协议端控制 ──

@router.get("/accounts", response_model=AccountListResponse)
def list_accounts():
    """获取所有已记录的 QQ 账号及当前状态。"""
    return account_manager.list_accounts()


@router.get("/accounts/login-status", response_model=AccountLoginStatus)
def get_account_login_status():
    """获取 NapCat 当前登录阶段，二维码只通过本地控制台转发。"""
    return account_manager.get_napcat_login_status()


@router.post("/accounts/quick-login")
def quick_login_account(payload: AccountQuickLoginRequest):
    """在 NapCat 已启动时尝试免密快速登录。"""
    return account_manager.quick_login(payload.qq)


@router.post("/accounts/switch")
def switch_account(payload: AccountSwitchRequest):
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
def set_default_account(payload: AccountSetDefaultRequest):
    """将指定账号设为默认启动账号。"""
    qq = payload.qq.strip()
    if not qq:
        raise HTTPException(status_code=400, detail="QQ 账号不能为空")
    account_manager.set_default_account(qq)
    account_manager.ensure_ws_config(qq)
    return {"success": True, "message": f"已设为默认账号: {qq}"}


@router.post("/accounts/launch")
def launch_account(payload: AccountLaunchRequest):
    """启动或重启 NapCat 进程（支持指定 QQ 或扫码模式）。"""
    return account_manager.launch_napcat(qq=payload.qq, qr_mode=payload.qr_mode)


@router.post("/accounts/stop")
def stop_napcat():
    """停止运行中的 NapCat/QQ 进程。"""
    ok = account_manager.stop_napcat()
    return {"success": ok, "message": "已发送停止进程指令"}


@router.post("/system/shutdown")
async def shutdown_system(payload: SystemShutdownRequest = SystemShutdownRequest()):
    """关闭或重启当前 ChatBot 进程，由本地启动器负责重新拉起。"""
    async def exit_soon() -> None:
        await asyncio.sleep(0.3)
        if payload.restart:
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "", str(ROOT_DIR / "start.bat")],
                cwd=str(ROOT_DIR),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        os._exit(0)

    asyncio.create_task(exit_soon())
    return {
        "success": True,
        "message": "正在重启 ChatBot" if payload.restart else "正在关闭 ChatBot",
    }


@router.post("/system/send-test")
async def send_test_message(payload: MessageSendRequest):
    """通过 ChatBot 网关发送测试私聊，验证发送链路。"""
    if not gateway.is_connected:
        raise HTTPException(status_code=409, detail="NapCat WebSocket 未连接")
    try:
        await gateway.send_private_message(payload.user_id, payload.message)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"success": True, "message": "测试消息已发送"}


@router.delete("/accounts/{qq}")
def delete_account(qq: str):
    """删除本地指定账号的配置文件。"""
    clean_qq = qq.strip()
    if gateway.is_connected and gateway.current_qq == clean_qq:
        raise HTTPException(status_code=400, detail="当前账号正在连接中，请先停止运行或切换账号后再删除")
    ok = account_manager.delete_account(clean_qq)
    return {"success": ok}


@router.get("/accounts/qrcode")
def get_qrcode():
    """获取扫码登录二维码图片。"""
    image = account_manager.get_qrcode_image()
    if not image:
        raise HTTPException(status_code=404, detail="未检测到有效二维码")
    return Response(content=image, media_type="image/png")


@router.post("/accounts/qrcode/refresh")
def refresh_qrcode():
    """向 NapCat 请求刷新登录二维码。"""
    return account_manager.refresh_qrcode()


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
        "last_event": gateway.last_event,
        "last_debouncer_state": gateway.last_debouncer_state,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
