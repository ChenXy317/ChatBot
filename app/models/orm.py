"""SQLAlchemy 数据库 ORM 模型定义。"""

from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Integer, String, Text, JSON
from sqlalchemy.orm import declarative_base
from app.engine.prompt_builder import DEFAULT_OUTPUT_PROMPT, DEFAULT_ROLE_PROMPT

Base = declarative_base()


class BotConfig(Base):
    """机器人全局运行时配置。"""
    __tablename__ = "bot_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_base = Column(String(255), default="https://api.deepseek.com/v1", nullable=False)
    api_key = Column(String(255), default="", nullable=False)
    model = Column(String(128), default="deepseek-chat", nullable=False)
    role_prompt = Column(Text, default=DEFAULT_ROLE_PROMPT, nullable=False)
    output_prompt = Column(Text, default=DEFAULT_OUTPUT_PROMPT, nullable=False)
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
