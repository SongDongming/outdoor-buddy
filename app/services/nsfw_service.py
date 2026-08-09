"""
本地 NSFW 图片审核服务
基于 Yahoo open_nsfw 的 onnxruntime 移植版（opennsfw-onnx），模型权重已内置在包内（open-nsfw.onnx，23MB）。
只检测色情类内容；暴力/政治等图片无法覆盖，靠用户举报 + 管理员人工兜底。

用法：get_score(image_bytes) → 0-1 概率；is_available() → 模型是否可用。
模型不可用（未安装依赖/加载失败）时优雅降级为 None，审核回退到"仅格式检查"。
"""
import threading
from io import BytesIO

from app.core.config import get_settings
from app.utils.logger import logger

_state = {"session": None, "available": None}
_load_lock = threading.Lock()


def _ensure_loaded() -> bool:
    """懒加载模型（进程级单例）。加载失败则标记不可用，避免重复尝试。"""
    if _state["session"] is not None:
        return True
    if _state["available"] is False:
        return False
    with _load_lock:
        if _state["session"] is not None:
            return True
        settings = get_settings()
        if not settings.nsfw_enabled:
            _state["available"] = False
            logger.info("[NSFW] nsfw_enabled=False，NSFW 审核已关闭")
            return False
        try:
            # classify() 内部维护懒加载单例，幂等
            from opennsfw_onnx import classify
            _state["session"] = classify
            _warmup()
            _state["available"] = True
            logger.info("[NSFW] open_nsfw 模型已加载（onnxruntime）")
            return True
        except Exception as e:
            _state["available"] = False
            logger.warning(f"[NSFW] 模型加载失败，NSFW 审核降级为不可用: {e}")
            return False


def _warmup() -> None:
    """用小图跑一次推理，触发模型加载 + 验证可用性"""
    try:
        from PIL import Image
        img = Image.new("RGB", (32, 32), (120, 160, 80))
        buf = BytesIO()
        img.save(buf, format="PNG")
        _state["session"](buf.getvalue())
    except Exception as e:
        logger.debug(f"[NSFW] warmup 未完成: {e}")


def is_available() -> bool:
    """模型是否可用"""
    return _ensure_loaded()


def get_score(image_bytes: bytes) -> float | None:
    """返回图片的 NSFW 概率（0-1）；模型不可用或解码失败返回 None"""
    if not _ensure_loaded():
        return None
    try:
        pred = _state["session"](image_bytes)
        return float(pred.nsfw)
    except Exception as e:
        logger.warning(f"[NSFW] 图片评分失败: {e}")
        return None
