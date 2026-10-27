"""数据传输对象 (DTO) 与 Pydantic 校验模型。"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class BotConfigBase(BaseModel):
    """全局配置基础字段。"""
    api_base: str = Field(..., description="OpenAI 兼容基础接口地址")
    api_key: str = Field(default="", description="API 密钥")
    model: str = Field(..., description="调用模型名称")
    role_prompt: str = Field(default="", description="机器人角色设定")
    output_prompt: str = Field(default="", description="输出要求与当前场景")
    temperature: float = Field(default=0.8, ge=0.0, le=2.0, description="采样温度")
    top_p: float = Field(default=0.9, ge=0.0, le=1.0, description="核采样比例")
    max_tokens: int = Field(default=2048, ge=64, le=16384, description="最大生成 Token 数量")
    debounce_delay: float = Field(default=1.5, ge=0.5, le=10.0, description="消息防抖缓冲秒数")
    typing_speed: float = Field(default=0.15, ge=0.01, le=1.0, description="单字拟人输入延迟秒数")
    is_enabled: bool = Field(default=True, description="是否开启自动接管")


class BotConfigRead(BotConfigBase):
    """配置读取响应。"""
    id: int
    updated_at: datetime
    api_key_set: bool = False

    class Config:
        from_attributes = True


class BotConfigUpdate(BaseModel):
    """配置修改请求。"""
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    role_prompt: Optional[str] = None
    output_prompt: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=64, le=16384)
    debounce_delay: Optional[float] = Field(default=None, ge=0.5, le=10.0)
    typing_speed: Optional[float] = Field(default=None, ge=0.01, le=1.0)
    is_enabled: Optional[bool] = None


class DeferredBotConfigUpdate(BotConfigUpdate):
    """允许控制台在编辑时提交空白密钥，保留数据库中的原密钥。"""
    api_key: Optional[str] = Field(default=None, description="留空时保留现有密钥")


class WhitelistUserCreate(BaseModel):
    """添加白名单用户。"""
    user_id: int = Field(..., description="好友 QQ 号")
    is_enabled: bool = Field(default=True, description="是否启用接管")
    custom_prompt: Optional[str] = Field(default=None, description="针对该好友的专属 Prompt")


class WhitelistUserUpdate(BaseModel):
    """更新白名单用户。"""
    is_enabled: Optional[bool] = None
    custom_prompt: Optional[str] = None


class WhitelistUserRead(BaseModel):
    """白名单读取响应。"""
    id: int
    user_id: int
    is_enabled: bool
    custom_prompt: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageRead(BaseModel):
    """聊天历史记录读取响应。"""
    id: int
    user_id: int
    role: str
    content: str
    image_urls: Optional[List[str]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageUpdate(BaseModel):
    """编辑聊天历史记录。"""
    content: str = Field(..., min_length=1, description="修改后的消息内容")
    image_urls: Optional[List[str]] = Field(default=None, description="图片 URL 列表")


class MessageOwnerRead(BaseModel):
    """拥有历史消息的好友及记录数量。"""
    user_id: int
    message_count: int
    last_message_at: Optional[datetime] = None


class SystemLogRead(BaseModel):
    """系统日志读取响应。"""
    id: int
    level: str
    source: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class TestConnectionRequest(BaseModel):
    """模型接口连通性测试请求。"""
    api_base: str
    api_key: str = ""
    api_key_set: bool = False
    model: str


class TestConnectionResponse(BaseModel):
    """模型接口连通性测试结果。"""
    success: bool
    latency_ms: float
    reply: str
    error: Optional[str] = None


class AccountItem(BaseModel):
    """单个 QQ 账号配置状态。"""
    qq: str
    is_online: bool
    is_default: bool
    has_ws_config: bool
    last_active: str


class AccountLoginStatus(BaseModel):
    """NapCat 登录阶段与二维码状态。"""
    available: bool
    is_login: bool
    login_phase: str
    login_error: str
    qrcode_url: str
    has_qrcode: bool = False


class AccountQuickLoginRequest(BaseModel):
    """通过 QQ 号触发 NapCat 快速登录。"""
    qq: str = Field(..., pattern=r"^[1-9]\d{4,10}$", description="目标 QQ 账号")


class AccountListResponse(BaseModel):
    """账号列表与运行状态响应。"""
    online_qq: Optional[str] = None
    online_nickname: Optional[str] = None
    is_connected: bool
    is_process_running: bool
    napcat_status: AccountLoginStatus
    default_account: Optional[str] = None
    accounts: List[AccountItem]


class AccountSwitchRequest(BaseModel):
    """切换账号请求。"""
    qq: str = Field(..., pattern=r"^[1-9]\d{4,10}$", description="目标 QQ 账号")
    auto_start: bool = Field(default=True, description="是否立即拉起启动")


class AccountSetDefaultRequest(BaseModel):
    """设定默认账号请求。"""
    qq: str = Field(..., pattern=r"^[1-9]\d{4,10}$", description="默认 QQ 账号")


class AccountLaunchRequest(BaseModel):
    """拉起 NapCat 实例请求。"""
    qq: Optional[str] = Field(default=None, pattern=r"^[1-9]\d{4,10}$")
    qr_mode: bool = False

