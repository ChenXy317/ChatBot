"""FastAPI 主应用入口，注册 WebSocket 网关、REST 路由与静态资源。"""

import ipaddress
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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


app = FastAPI(
    title="QQ ChatBot Agent",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def is_dashboard_request_authorized(headers) -> bool:
    """控制台 API 只接受显式配置的本地口令。"""
    if not settings.dashboard_auth_required:
        return True
    supplied = headers.get("x-dashboard-token", "").strip()
    return bool(supplied) and secrets.compare_digest(supplied, settings.DASHBOARD_TOKEN)


def client_is_loopback(host: str) -> bool:
    """控制台只允许本机访问，即便服务器绑定到了局域网地址。"""
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback
    except ValueError:
        return host in {"localhost", "testclient"}


@app.middleware("http")
async def protect_dashboard_api(request: Request, call_next):
    if not client_is_loopback(request.client.host):
        return JSONResponse({"detail": "Local access only"}, status_code=403)
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    if request.url.path == "/api/auth/check":
        if not settings.dashboard_auth_required:
            return JSONResponse({"required": False})
        if not is_dashboard_request_authorized(request.headers):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return JSONResponse({"required": True})
    if not is_dashboard_request_authorized(request.headers):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


@app.get("/api/auth/check")
async def dashboard_auth_check():
    """前端启动时确认是否需要控制台口令。"""
    return {"required": settings.dashboard_auth_required}

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", f"http://127.0.0.1:{settings.SERVER_PORT}", f"http://localhost:{settings.SERVER_PORT}"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-Dashboard-Token"],
)

# 注册 API 路由
app.include_router(api_router)


# OneBot v11 反向 WebSocket 接入端点
@app.websocket("/ws/qq")
async def qq_websocket_endpoint(websocket: WebSocket):
    if not client_is_loopback(websocket.client.host if websocket.client else ""):
        await websocket.close(code=1008, reason="Local access only")
        return
    if not is_dashboard_request_authorized(websocket.headers):
        await websocket.close(code=1008, reason="Unauthorized")
        return
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
