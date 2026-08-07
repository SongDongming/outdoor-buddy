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


async def ensure_forum_reply_parent_column() -> None:
    """
    幂等迁移：为 forum_replies 表补充 parent_id 列（嵌套回复）
    PostgreSQL 用 IF NOT EXISTS；SQLite 不支持该语法，用 try/except 忽略重复列
    """
    from sqlalchemy import text
    engine = _get_engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE forum_replies ADD COLUMN IF NOT EXISTS parent_id INTEGER"))
        logger.info("[MIGRATE] forum_replies.parent_id 就绪")
        return
    except Exception:
        pass
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE forum_replies ADD COLUMN parent_id INTEGER"))
        logger.info("[MIGRATE] forum_replies.parent_id 就绪")
    except Exception as e:
        logger.warning(f"[MIGRATE] forum_replies.parent_id 迁移跳过（可能已存在）: {e}")


async def ensure_user_columns() -> None:
    """
    幂等迁移：为 users 表补充当前模型缺失的列（兼容旧 schema 的数据库）
    仅补充列，不修改已有数据
    """
    from sqlalchemy import text
    engine = _get_engine()
    additions = [
        ("email", "VARCHAR(255)"),
        ("email_verified", "BOOLEAN DEFAULT false"),
        ("reset_token", "VARCHAR(255)"),
        ("reset_token_expires", "TIMESTAMP WITH TIME ZONE"),
    ]
    for name, ddl in additions:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
            logger.info(f"[MIGRATE] users.{name} 已补充")
        except Exception:
            # 列已存在或语法不支持时跳过
            logger.debug(f"[MIGRATE] users.{name} 已存在，跳过")


async def ensure_forum_reply_like_column() -> None:
    """幂等迁移：为 forum_replies 表补充 like_count 列（评论点赞）"""
    from sqlalchemy import text
    engine = _get_engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE forum_replies ADD COLUMN IF NOT EXISTS like_count INTEGER DEFAULT 0"))
        logger.info("[MIGRATE] forum_replies.like_count 就绪")
        return
    except Exception:
        pass
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE forum_replies ADD COLUMN like_count INTEGER DEFAULT 0"))
        logger.info("[MIGRATE] forum_replies.like_count 就绪")
    except Exception as e:
        logger.warning(f"[MIGRATE] forum_replies.like_count 迁移跳过: {e}")


async def close_db() -> None:
    """关闭数据库连接"""
    if _engine:
        await _engine.dispose()
    await _fallback_engine.dispose()


def is_db_available() -> bool:
    """检查 PostgreSQL 是否可用"""
    return _db_available