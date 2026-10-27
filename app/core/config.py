"""核心基础配置与环境变量加载。"""

import os
import secrets
import stat
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TOKEN_FILE = BASE_DIR / "napcat" / ".onebot_ws_token"

# 加载项目根目录 .env 文件
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    """应用全局配置。"""
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "qq_chatbot")

    SERVER_HOST: str = os.getenv("SERVER_HOST", "127.0.0.1")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8090"))
    DASHBOARD_TOKEN: str = os.getenv("DASHBOARD_TOKEN", "")
    ONEBOT_WS_TOKEN: str = os.getenv("ONEBOT_WS_TOKEN", "")

    def __init__(self, **values):
        super().__init__(**values)
        if not self.ONEBOT_WS_TOKEN:
            self.ONEBOT_WS_TOKEN = self._load_or_create_ws_token()

    @staticmethod
    def _load_or_create_ws_token() -> str:
        """在本地保存自动生成的 OneBot token，避免重启后配置失配。"""
        try:
            if TOKEN_FILE.is_file():
                token = TOKEN_FILE.read_text(encoding="utf-8").strip()
                if token:
                    return token
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            token = secrets.token_urlsafe(24)
            TOKEN_FILE.write_text(token, encoding="utf-8")
            try:
                TOKEN_FILE.chmod(stat.S_IREAD | stat.S_IWRITE)
            except OSError:
                pass
            return token
        except OSError:
            return secrets.token_urlsafe(24)

    @property
    def dashboard_auth_required(self) -> bool:
        """是否要求浏览器控制台携带本地访问口令。"""
        return bool(self.DASHBOARD_TOKEN)

    @property
    def async_db_url(self) -> str:
        """异步 MySQL 数据库连接串。"""
        encoded_password = quote_plus(self.MYSQL_PASSWORD)
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{encoded_password}@"
            f"{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"
        )


settings = Settings()
