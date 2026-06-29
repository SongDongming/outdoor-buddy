"""
数据库连接管理模块
提供 SQLAlchemy 异步引擎、会话工厂及基础模型类
支持 PostgreSQL 优先，连接失败时自动降级到 SQLite
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings
from app.utils.logger import logger

settings = get_settings()

# 数据库是否可用
_db_available = False

# 尝试 PostgreSQL，失败则降级到 SQLite
_engine = None
try:
    _engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        connect_args={"timeout": 5},
    )
except Exception as e:
    logger.warning(f"PostgreSQL 引擎创建失败，降级到 SQLite: {e}")

# SQLite 降级引擎（备用）
_sqlite_url = "sqlite+aiosqlite:///./outdoor_buddy.db"
_fallback_engine = create_async_engine(_sqlite_url, echo=False)


def _get_engine():
    """获取当前可用的引擎"""
    global _db_available
    if _db_available and _engine:
        return _engine
    return _fallback_engine


# 异步会话工厂
async_session_factory = async_sessionmaker(
    _get_engine(),
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    engine = _get_engine()
    # 动态更新 session factory 的引擎
    current_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with current_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库表结构"""
    global _db_available, async_session_factory

    # 先尝试 PostgreSQL
    if _engine:
        try:
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _db_available = True
            async_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
            logger.info("[OK] PostgreSQL 数据库连接成功，表结构已就绪")
            return
        except Exception as e:
            logger.warning(f"[WARN] PostgreSQL 连接失败: {e}")

    # 降级到 SQLite
    try:
        async with _fallback_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_available = False
        async_session_factory = async_sessionmaker(_fallback_engine, class_=AsyncSession, expire_on_commit=False)
        logger.info("[OK] SQLite 降级数据库已就绪（开发模式）")
        logger.info("[WARN] 生产环境请配置 PostgreSQL: 确保数据库 outdoor_assistant 已创建且服务运行中")
    except Exception as e:
        logger.error(f"[ERROR] SQLite 初始化也失败: {e}")
        raise


async def close_db() -> None:
    """关闭数据库连接"""
    if _engine:
        await _engine.dispose()
    await _fallback_engine.dispose()


def is_db_available() -> bool:
    """检查 PostgreSQL 是否可用"""
    return _db_available