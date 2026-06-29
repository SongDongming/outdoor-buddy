"""
FastAPI 应用入口
初始化应用、注册路由、配置 CORS、管理生命周期
"""
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import get_settings
from app.models.database import init_db, close_db, is_db_available
from app.utils.logger import logger

# 导入所有路由模块
from app.api import auth, routes, qa, equipment, tickets, weather, plans, favorites, global_interaction, forum
from app.services.storage_service import get_storage

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print(f"[START] {settings.app_name} v{settings.app_version}")
    logger.info(f"[START] {settings.app_name} v{settings.app_version} 启动中...")
    try:
        await init_db()
    except Exception as e:
        logger.error(f"[ERROR] 数据库初始化失败: {e}")
        print(f"[ERROR] DB init failed: {e}")
    try:
        storage = get_storage()
        logger.info(f"[OK] 存储后端: {storage.__class__.__name__}")
        print(f"[OK] 存储后端: {storage.__class__.__name__}")
    except Exception as e:
        logger.error(f"[ERROR] 存储后端初始化失败: {e}")
        print(f"[ERROR] Storage init failed: {e}")
    yield
    await close_db()
    print("[STOP] 应用已关闭")
    logger.info("[STOP] 应用已关闭")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于大模型的一站式户外徒步智能助手",
    lifespan=lifespan,
)

# 请求日志中间件 — 用 print() 确保在 reload 模式下可见
import sys
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    if "/api/" in request.url.path:
        msg = f"[API] {request.method} {request.url.path} -> {response.status_code} ({duration:.2f}s)"
        print(msg, flush=True)
        logger.info(msg)
    return response

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(auth.router)
app.include_router(routes.router)
app.include_router(qa.router)
app.include_router(equipment.router)
app.include_router(tickets.router)
app.include_router(weather.router)
app.include_router(plans.router)
app.include_router(favorites.router)
app.include_router(global_interaction.router)
app.include_router(forum.router)

# 静态文件服务
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", tags=["前端入口"])
async def root():
    """前端首页"""
    return FileResponse("app/static/index.html")


@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查接口"""
    storage = get_storage()
    return {
        "status": "healthy",
        "database": "postgresql" if is_db_available() else "sqlite_fallback",
        "storage": storage.__class__.__name__,
        "version": settings.app_version,
    }