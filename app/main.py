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
from app.models.database import init_db, close_db, is_db_available, ensure_forum_reply_parent_column, ensure_forum_reply_like_column, ensure_user_columns, ensure_moderation_columns, ensure_forum_indexes
from app.utils.logger import logger

# 导入所有路由模块（moderation 模块会注册 app.models.moderation，确保建表）
from app.api import auth, routes, qa, equipment, tickets, weather, plans, favorites, forum, moderation, export
from app.services.storage_service import get_storage
from app.utils.redis_client import init_redis, close_redis

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print(f"[START] {settings.app_name} v{settings.app_version}")
    logger.info(f"[START] {settings.app_name} v{settings.app_version} 启动中...")

    # 安全校验：使用默认密钥/默认超管口令时给出醒目告警
    if settings.secret_key == "outdoor-buddy-secret-key-change-in-production":
        msg = "[SECURITY] 正在使用默认 SECRET_KEY！生产环境请设置随机密钥，否则令牌可被伪造（.env 中 SECRET_KEY）"
        logger.warning(msg); print(f"\n\033[33m{msg}\033[0m\n")
    if settings.super_admin_password == "admin123":
        msg = "[SECURITY] 超管口令仍是默认 admin123！请立即在 .env 中修改 SUPER_ADMIN_PASSWORD"
        logger.warning(msg); print(f"\033[33m{msg}\033[0m\n")

    try:
        await init_db()
    except Exception as e:
        logger.error(f"[ERROR] 数据库初始化失败: {e}")
        print(f"[ERROR] DB init failed: {e}")
    try:
        # 幂等迁移：补 forum_replies.parent_id / like_count 列 + users 缺失列 + 审核列/表
        await ensure_forum_reply_parent_column()
        await ensure_forum_reply_like_column()
        await ensure_user_columns()
        await ensure_moderation_columns()
        await ensure_forum_indexes()
        print("[OK] 数据库迁移检查完成")
    except Exception as e:
        logger.warning(f"[WARN] 数据库迁移失败: {e}")
        print(f"[WARN] Migration failed: {e}")
    try:
        # 确保超管账号存在（幂等）
        # 注意: 须在 init_db 之后导入，才能拿到切换后的当前引擎会话工厂
        from app.models.database import async_session_factory
        async with async_session_factory() as session:
            from app.services.admin_service import ensure_admin_user
            await ensure_admin_user(session)
        print("[OK] 超管账号检查完成")
        logger.info("[OK] 超管账号检查完成")
    except Exception as e:
        logger.error(f"[ERROR] 超管账号初始化失败: {e}")
        print(f"[ERROR] Admin init failed: {e}")
    try:
        storage = get_storage()
        logger.info(f"[OK] 存储后端: {storage.__class__.__name__}")
        print(f"[OK] 存储后端: {storage.__class__.__name__}")
    except Exception as e:
        logger.error(f"[ERROR] 存储后端初始化失败: {e}")
        print(f"[ERROR] Storage init failed: {e}")
    try:
        await init_redis()
    except Exception as e:
        logger.warning(f"[WARN] Redis 初始化失败: {e}")
        print(f"[WARN] Redis init failed: {e}")
    yield
    await close_redis()
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
import sys, traceback
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


# 全局异常处理：记录堆栈、返回统一响应（不泄露内部信息）
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    logger.error(f"[ERROR] 未处理异常 {request.method} {request.url.path}: {exc}")
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误，请稍后重试", "data": None},
    )

# CORS 配置（前端同源部署，收窄允许来源；可按需在 CORS_ORIGINS 配置额外来源）
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["http://localhost:8001"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 安全响应头（CSP / X-Frame-Options 等，对 XSS 提供第二道防线）
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob: https://img.outdoorbuddy.top; "
        "connect-src 'self'; "
        "frame-ancestors 'none'",
    )
    return response

# 注册 API 路由
app.include_router(auth.router)
app.include_router(routes.router)
app.include_router(qa.router)
app.include_router(equipment.router)
app.include_router(tickets.router)
app.include_router(weather.router)
app.include_router(plans.router)
app.include_router(favorites.router)
app.include_router(forum.router)
app.include_router(moderation.router)
app.include_router(export.router)

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