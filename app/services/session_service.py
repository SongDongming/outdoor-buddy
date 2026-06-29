"""
会话上下文管理服务
实现会话级上下文记忆，支持多轮对话、指代式提问和参数修正
"""
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.session_context import SessionContext
from app.utils.logger import logger

# 内存缓存层，减少数据库查询
_memory_cache: dict[str, dict] = {}


async def get_session_context(session_id: str, db: AsyncSession) -> list[dict]:
    """
    获取会话上下文
    优先从内存缓存读取，其次从数据库
    """
    # 1. 内存缓存
    if session_id in _memory_cache:
        return _memory_cache[session_id].get("context", [])

    # 2. 数据库查询
    result = await db.execute(
        select(SessionContext).where(SessionContext.session_id == session_id)
    )
    session = result.scalar_one_or_none()

    if session and session.context_data:
        context = session.context_data.get("context", [])
        # 同步到内存缓存
        _memory_cache[session_id] = {
            "context": context,
            "query_results": session.context_data.get("query_results", {}),
        }
        return context

    return []


async def update_session_context(
    session_id: str,
    context: list[dict],
    user_id: int | None,
    db: AsyncSession,
) -> None:
    """
    更新会话上下文，同时更新内存缓存和数据库
    """
    # 1. 更新内存缓存
    if session_id not in _memory_cache:
        _memory_cache[session_id] = {}
    _memory_cache[session_id]["context"] = context

    # 2. 更新数据库
    try:
        result = await db.execute(
            select(SessionContext).where(SessionContext.session_id == session_id)
        )
        session = result.scalar_one_or_none()

        if session:
            session.context_data = _memory_cache[session_id]
            session.updated_at = datetime.now(timezone.utc)
        else:
            session = SessionContext(
                session_id=session_id,
                user_id=user_id,
                context_data=_memory_cache[session_id],
            )
            db.add(session)
        await db.flush()
    except Exception as e:
        logger.error(f"会话上下文保存失败: {e}")


async def store_query_result(
    session_id: str,
    query_type: str,
    result_key: str,
    result_data: dict,
    db: AsyncSession,
) -> None:
    """
    在会话中存储查询结果，支持指代式提问
    query_type: route, weather, ticket, equipment, plan
    """
    if session_id not in _memory_cache:
        _memory_cache[session_id] = {"context": [], "query_results": {}}

    _memory_cache[session_id]["query_results"][result_key] = {
        "type": query_type,
        "data": result_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # 持久化
    result = await db.execute(
        select(SessionContext).where(SessionContext.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if session:
        session.context_data = _memory_cache[session_id]
        session.updated_at = datetime.now(timezone.utc)
        await db.flush()


def get_session_query_results(session_id: str) -> dict:
    """获取会话中已存储的查询结果"""
    if session_id in _memory_cache:
        return _memory_cache[session_id].get("query_results", {})
    return {}


def clear_session(session_id: str) -> None:
    """清除会话"""
    if session_id in _memory_cache:
        del _memory_cache[session_id]