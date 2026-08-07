"""
路线查询服务模块
提供路线搜索结果的缓存读写（Redis 优先，DB 兜底）
"""
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.route_cache import RouteCache
from app.utils.redis_client import redis_get, redis_set
from app.utils.logger import logger

# 路线缓存有效期（24小时）
ROUTE_CACHE_TTL_HOURS = 24


async def _get_cached_route(keyword: str, db: AsyncSession) -> dict | None:
    """从缓存获取路线数据（Redis 优先，DB 兜底）"""
    # Redis 优先
    cached = await redis_get(f"route:{keyword}")
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    # DB 兜底
    await db.execute(
        delete(RouteCache).where(RouteCache.expires_at < datetime.now(timezone.utc))
    )
    result = await db.execute(
        select(RouteCache)
        .where(RouteCache.keyword == keyword)
        .where(RouteCache.expires_at > datetime.now(timezone.utc))
        .order_by(RouteCache.created_at.desc())
        .limit(1)
    )
    cache_entry = result.scalar_one_or_none()
    if cache_entry:
        return cache_entry.route_data
    return None


async def _cache_route(keyword: str, data: dict, db: AsyncSession) -> None:
    """将路线数据写入缓存（Redis 优先成功则跳过 DB 写，减轻数据库负担）"""
    # Redis 优先
    if await redis_set(f"route:{keyword}", json.dumps(data, ensure_ascii=False), ROUTE_CACHE_TTL_HOURS * 3600):
        logger.info(f"路线缓存写入(Redis): {keyword}")
        return

    # DB 兜底
    try:
        cache_entry = RouteCache(
            keyword=keyword,
            route_data=data,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ROUTE_CACHE_TTL_HOURS),
        )
        db.add(cache_entry)
        await db.flush()
        logger.info(f"路线缓存写入(DB): {keyword}")
    except Exception as e:
        logger.error(f"路线缓存写入失败: {e}")


