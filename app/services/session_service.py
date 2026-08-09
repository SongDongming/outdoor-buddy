"""
会话上下文管理服务
实现会话级上下文记忆，支持多轮对话、指代式提问和参数修正
缓存策略: Redis 优先（多 worker 共享、减 DB 负担）→ 内存 → 数据库
"""
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.session_context import SessionContext
from app.utils.redis_client import redis_get, redis_set
from app.utils.logger import logger

# 内存缓存层（单 worker 生效；Redis 不可用时降级用）
_memory_cache: dict[str, dict] = {}
# 会话上下文 TTL（24 小时）
_SESSION_TTL = 24 * 3600
# 内存缓存上限（防恶意 session_id 无限膨胀）
_MEMORY_CACHE_MAX = 5000


def _session_key(session_id: str) -> str:
    return f"session:{session_id}"


def _cache_put(session_id: str, data: dict) -> None:
    """写入内存缓存；超上限时淘汰最早插入的键（dict 保持插入序）"""
    if len(_memory_cache) >= _MEMORY_CACHE_MAX and session_id not in _memory_cache:
        try:
            _memory_cache.pop(next(iter(_memory_cache)))
        except StopIteration:
            pass
    _memory_cache[session_id] = data


async def get_session_context(session_id: str, db: AsyncSession) -> list[dict]:
    """
    获取会话上下文
    Redis → 内存缓存 → 数据库 三级读取
    """
    # 1. Redis（多 worker 共享）
    cached = await redis_get(_session_key(session_id))
    if cached:
        try:
            return json.loads(cached).get("context", [])
        except Exception:
            pass

    # 2. 内存缓存
    if session_id in _memory_cache:
        return _memory_cache[session_id].get("context", [])

    # 3. 数据库查询
    result = await db.execute(
        select(SessionContext).where(SessionContext.session_id == session_id)
    )
    session = result.scalar_one_or_none()

    if session and session.context_data:
        context = session.context_data.get("context", [])
        data = {
            "context": context,
            "query_results": session.context_data.get("query_results", {}),
        }
        # 同步到内存缓存和 Redis
        _cache_put(session_id, data)
        await redis_set(_session_key(session_id), json.dumps(data, ensure_ascii=False), _SESSION_TTL)
        return context

    return []


async def update_session_context(
    session_id: str,
    context: list[dict],
    user_id: int | None,
    db: AsyncSession,
) -> None:
    """
    更新会话上下文
    Redis 可用时写 Redis（跳过 DB 写，减轻数据库负担）；否则更新内存缓存 + 数据库
    """
    data = {
        "context": context,
        "query_results": _memory_cache.get(session_id, {}).get("query_results", {}),
    }

    # Redis 优先
    if await redis_set(_session_key(session_id), json.dumps(data, ensure_ascii=False), _SESSION_TTL):
        _cache_put(session_id, data)
        return

    # DB 兜底
    _cache_put(session_id, data)
    try:
        result = await db.execute(
            select(SessionContext).where(SessionContext.session_id == session_id)
        )
        session = result.scalar_one_or_none()

        if session:
            session.context_data = data
            session.updated_at = datetime.now(timezone.utc)
        else:
            session = SessionContext(
                session_id=session_id,
                user_id=user_id,
                context_data=data,
            )
            db.add(session)
        await db.flush()
    except Exception as e:
        logger.error(f"会话上下文保存失败: {e}")


