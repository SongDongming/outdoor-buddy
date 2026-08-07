"""
Redis 客户端模块
异步 Redis 客户端，惰性初始化；不可用时优雅降级（返回 None/False，调用方回退到 DB/内存）
环境无 redis 库（如旧 Docker 镜像）时也不会导致应用崩溃
"""
from typing import Optional

from app.core.config import get_settings
from app.utils.logger import logger

# redis 库不可用时不崩
try:
    import redis.asyncio as _aioredis
    _REDIS_LIB = True
except ImportError:
    _aioredis = None
    _REDIS_LIB = False

_settings = get_settings()
_redis: Optional[object] = None
_checked = False
_available = False

# 统一超时，避免 Redis 挂起拖慢业务
_CONNECT_TIMEOUT = 2
_SOCKET_TIMEOUT = 3


async def init_redis() -> bool:
    """初始化 Redis 并 ping 探测可用性；幂等"""
    global _redis, _checked, _available
    if _checked:
        return _available
    _checked = True
    if not _REDIS_LIB or not _settings.redis_url:
        logger.warning("[Redis] 未启用（库或配置缺失），降级到 DB/内存缓存")
        return False
    try:
        _redis = _aioredis.from_url(
            _settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=_CONNECT_TIMEOUT,
            socket_timeout=_SOCKET_TIMEOUT,
        )
        await _redis.ping()
        _available = True
        logger.info("[Redis] 连接成功")
    except Exception as e:
        _available = False
        logger.warning(f"[Redis] 不可用，降级到 DB/内存缓存: {e}")
    return _available


def redis_available() -> bool:
    """Redis 是否可用"""
    return _available


async def redis_get(key: str) -> Optional[str]:
    """读取字符串值，失败返回 None"""
    if not _available or _redis is None:
        return None
    try:
        return await _redis.get(key)
    except Exception:
        return None


async def redis_set(key: str, value: str, ttl: int) -> bool:
    """写入字符串值并设 TTL（秒），成功返回 True"""
    if not _available or _redis is None:
        return False
    try:
        await _redis.set(key, value, ex=ttl)
        return True
    except Exception:
        return False


async def redis_incr(key: str, ttl: int) -> Optional[int]:
    """自增并设 TTL，返回计数；失败返回 None"""
    if not _available or _redis is None:
        return None
    try:
        count = await _redis.incr(key)
        await _redis.expire(key, ttl)
        return count
    except Exception:
        return None


async def redis_del(key: str) -> bool:
    """删除键，成功返回 True"""
    if not _available or _redis is None:
        return False
    try:
        await _redis.delete(key)
        return True
    except Exception:
        return False


async def close_redis() -> None:
    """关闭 Redis 连接"""
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None
