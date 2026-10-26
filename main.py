"""FastAPI 主应用入口，注册 WebSocket 网关、REST 路由与静态资源。"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as api_router
from app.core.config import settings
from app.core.database import engine, init_db
from app.engine.debouncer import MessageDebouncer
from app.gateway.onebot_ws import gateway

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：初始化数据库与注册核心调度器。"""
    logger.info("正在初始化数据库与加载配置...")
    await init_db()

    debouncer = MessageDebouncer(
        send_message_fn=gateway.send_private_message,
        set_status_fn=gateway.set_input_status,
    )
    gateway.set_debouncer(debouncer)
    logger.info("消息防抖与打断调度器已就绪")

    yield

    logger.info("服务关闭，释放数据库连接池...")
    await engine.dispose()


app = FastAPI(title="QQ ChatBot Agent", lifespan=lifespan)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(api_router)


# OneBot v11 反向 WebSocket 接入端点
@app.websocket("/ws/qq")
async def qq_websocket_endpoint(websocket: WebSocket):
    await gateway.handle_websocket(websocket)


# 挂载 Web 控制台前端静态资源
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    async def index_page():
        return FileResponse(str(WEB_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=False,
    )
