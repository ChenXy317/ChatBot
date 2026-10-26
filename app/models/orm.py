"""SQLAlchemy 数据库 ORM 模型定义。"""

from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Integer, String, Text, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class BotConfig(Base):
    """机器人全局运行时配置。"""
    __tablename__ = "bot_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_base = Column(String(255), default="https://api.deepseek.com/v1", nullable=False)
    api_key = Column(String(255), default="", nullable=False)
    model = Column(String(128), default="deepseek-chat", nullable=False)
    system_prompt = Column(
        Text,
        default=(
            "你现在正在 QQ 上与好友私聊。\n"
            "【行为规范】\n"
            "1. 语言口语化、随性自然，像日常真人聊天。\n"
            "2. 严禁使用任何 Markdown 格式（严禁出现 **加粗**、标题、序号列表或代码块）。\n"
            "3. 按照真人打字习惯，将回复拆分成 1~3 条短消息，每条短消息单独成行（用换行符分隔）。\n"
            "4. 单条短消息控制在 5~30 个字以内，切勿长篇大论。\n"
            "5. 严禁暴露自己是 AI 或语言模型。\n"
            "6. 严禁输出任何思考过程或思维链（严禁出现 <think>、<thought> 等思考标签），必须直接输出真实对话。"
        ),
        nullable=False
    )
    temperature = Column(Float, default=0.8, nullable=False)
    top_p = Column(Float, default=0.9, nullable=False)
    max_tokens = Column(Integer, default=2048, nullable=False)
    debounce_delay = Column(Float, default=1.5, nullable=False)
    typing_speed = Column(Float, default=0.15, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class WhitelistUser(Base):
    """好友接管白名单。"""
    __tablename__ = "whitelist_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, unique=True, index=True, nullable=False)
    remark = Column(String(64), default="", nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    custom_prompt = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class ChatMessage(Base):
    """聊天历史记录。"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, index=True, nullable=False)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    image_urls = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True, nullable=False)


class SystemLog(Base):
    """系统运行日志记录。"""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(16), default="INFO", nullable=False)
    source = Column(String(32), default="SYSTEM", nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now, index=True, nullable=False)
