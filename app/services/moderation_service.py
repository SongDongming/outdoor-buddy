"""
内容审核服务 — 关键词秒拦 + 本地 NSFW 图片检测 + DeepSeek 后台文字复查

分层职责：
- check_text()    L1 关键词黑名单（本地即时，命中即拒绝发布）
- check_image()   L2 本地 NSFW 模型（reject 直接拦截 / flagged 入复核队列 / ok 放行）
- review_content_async()  L3 后台异步：图片 NSFW 复核 + DeepSeek 文本复查，可疑内容写入审核队列

结果动作约定：action ∈ {ok, flagged, reject}
"""
import asyncio
import os
from dataclasses import dataclass
from typing import Optional

from app.core.config import get_settings
from app.utils.logger import logger
from app.utils.aho_corasick import AhoCorasick

# ==============================
# 结果类型
# ==============================

@dataclass
class ModerationResult:
    """一次审核的结果"""
    action: str            # ok / flagged / reject
    reason: str = ""       # 简要原因
    score: Optional[float] = None  # NSFW 概率 / AI 评分
    source: str = "keyword"  # keyword / nsfw / ai


# ==============================
# L1 关键词黑名单
# ==============================

_KEYWORDS: list[str] = []
_KEYWORDS_LOWER: list[str] = []
_matcher: Optional[AhoCorasick] = None
_keywords_lock = asyncio.Lock()


def _keywords_file() -> str:
    """手工维护的关键词文件路径（相对本文件定位，与 CWD 无关）"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "data", "moderation_keywords.txt",
    )


def _lexicon_dir() -> str:
    """精选敏感词库目录（Sensitive-lexicon 精选子集，按分类一个文件）"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "data", "lexicon",
    )


def _load_word_files(paths: list[str]) -> list[str]:
    """从多个词表文件读取关键词（# 开头为注释行，空行跳过）"""
    kws: list[str] = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    kws.append(line)
        except FileNotFoundError:
            logger.warning(f"[审核] 词表文件不存在: {path}")
    return kws


def reload_keywords() -> None:
    """
    重新加载关键词黑名单 + 精选词库，并重建 Aho-Corasick 自动机。
    启动时 + 管理员热更新时调用。
    """
    global _KEYWORDS, _KEYWORDS_LOWER, _matcher

    # 收集词表文件：手工维护的黑名单 + 词库目录下的所有 .txt 分类文件
    files = [_keywords_file()]
    ldir = _lexicon_dir()
    if os.path.isdir(ldir):
        for fn in sorted(os.listdir(ldir)):
            if fn.endswith(".txt"):
                files.append(os.path.join(ldir, fn))

    kws = _load_word_files(files)
    _KEYWORDS = kws
    _KEYWORDS_LOWER = [k.lower() for k in kws]
    # 重建 AC 自动机（多模式匹配，O(文本长度)，词量增大不影响速度）
    _matcher = AhoCorasick(_KEYWORDS_LOWER)
    logger.info(f"[审核] 关键词黑名单已加载: {len(kws)} 条（词库分类 {len(files)-1} 个）")


def check_text(text: str) -> ModerationResult:
    """关键词即时拦截（Aho-Corasick 多模式匹配）。命中 → reject（统一提示，不泄露具体词）"""
    global _matcher
    if _matcher is None:
        reload_keywords()
    if not text:
        return ModerationResult(action="ok", reason="", source="keyword")
    if _matcher.contains(text.lower()):
        return ModerationResult(action="reject", reason="内容包含违规词汇", score=None, source="keyword")
    return ModerationResult(action="ok", reason="", source="keyword")


# ==============================
# L2 本地 NSFW 图片检测
# ==============================

def check_image(content: bytes) -> ModerationResult:
    """NSFW 图片检测：reject(≥阈值直接拦截) / flagged(入复核队列) / ok"""
    settings = get_settings()
    if not settings.nsfw_enabled:
        return ModerationResult(action="ok", reason="NSFW 未启用", source="nsfw")

    # 解压炸弹防护：小体积超大像素图直接拒绝（解码前先读头部取尺寸）
    try:
        from PIL import Image
        from io import BytesIO
        with Image.open(BytesIO(content)) as img:
            w, h = img.size
        if w * h > 40_000_000:  # > 40MP
            return ModerationResult(action="reject", reason="图片尺寸过大", score=None, source="nsfw")
    except Exception:
        pass  # 非图片或读取失败交给 NSFW 模型处理

    from app.services.nsfw_service import get_score
    score = get_score(content)
    if score is None:
        # 模型不可用 → 无法检测，放行（不误伤正常内容）
        return ModerationResult(action="ok", reason="模型不可用", source="nsfw")

    if score >= settings.nsfw_reject_threshold:
        return ModerationResult(
            action="reject", reason="图片涉嫌违规内容，已拦截", score=score, source="nsfw"
        )
    if score >= settings.nsfw_review_threshold:
        return ModerationResult(
            action="flagged", reason="图片疑似违规，待人工复核", score=score, source="nsfw"
        )
    return ModerationResult(action="ok", reason="", score=score, source="nsfw")


# ==============================
# L3 后台异步复查（图片复核 + DeepSeek 文本）
# ==============================

_TEXT_REVIEW_PROMPT = """你是内容安全审核专家。请审核以下户外徒步论坛的文本内容是否违规。
违规判定：1.色情低俗裸露 2.暴力血腥 3.政治敏感 4.广告/诈骗/赌博 5.辱骂歧视。
若内容正常，输出：{"passed": true}
若违规，输出：{"passed": false, "reason": "简述违规点（20字内）", "score": 1-10}
只允许输出上述 JSON，不要输出其他内容。"""


def _extract_json(text: str) -> dict:
    """从模型输出中容错提取 JSON 对象"""
    import json
    s = text.find("{")
    e = text.rfind("}") + 1
    if s >= 0 and e > s:
        try:
            return json.loads(text[s:e])
        except Exception:
            pass
    return {}


async def _add_record(target_type: str, target_id: int, source: str, score, reason: str) -> None:
    """独立会话写入一条审核队列记录（后台任务专用，函数内导入避免捕获旧引用）"""
    try:
        from app.models.database import async_session_factory
        from app.models.moderation import ModerationRecord
        async with async_session_factory() as session:
            session.add(ModerationRecord(
                target_type=target_type, target_id=target_id,
                report_reason=f"{source}_flagged",
                source=source, ai_score=score, ai_reason=reason or None,
                status="pending",
            ))
            await session.commit()
    except Exception as e:
        logger.warning(f"[审核] 写入队列记录失败 ({target_type}#{target_id}): {e}")


async def _read_image_bytes(url: str) -> bytes:
    """从本地存储读取图片字节（仅接受本站 /static/img/ 路径，防 SSRF 与路径穿越）"""
    settings = get_settings()
    if not url.startswith("/static/img/"):
        return b""  # 非本站路径：拒绝远程/外部 URL（防 SSRF）
    rel = url[len("/static/img/"):]
    # 防路径穿越
    if rel.startswith("..") or ".." in rel.split("/"):
        return b""
    base = os.path.abspath(settings.storage_local_dir)
    path = os.path.normpath(os.path.join(base, rel))
    if not (path == base or path.startswith(base + os.sep)):
        return b""  # 解析后越出存储目录：拒绝
    return await asyncio.to_thread(_read_local_file, path)


def _read_local_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


async def review_content_async(content: str, image_urls: list[str], target_type: str, target_id: int) -> None:
    """
    后台异步复查：已通过即时拦截的内容，进一步做
    1) 图片 NSFW 复核（边界图片入复核队列）
    2) DeepSeek 文本语义复查（判定违规入复核队列）
    任何异常只记日志，不影响主流程。
    """
    logger.info(f"[审核] 开始后台复查: {target_type}#{target_id}")
    try:
        # 1. 图片复核
        for url in (image_urls or [])[:4]:
            try:
                data = await _read_image_bytes(url)
            except Exception as e:
                logger.debug(f"[审核] 图片读取失败跳过 {url}: {e}")
                continue
            # onnx 推理放线程池，避免阻塞事件循环
            res = await asyncio.to_thread(check_image, data)
            if res.action == "flagged" and res.score is not None:
                await _add_record(target_type, target_id, "nsfw", res.score, res.reason)

        # 2. 文本语义复查
        if content:
            settings = get_settings()
            if not settings.compatible_api_key:
                return
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.compatible_api_key, base_url=settings.compatible_base_url, timeout=20)
            resp = await client.chat.completions.create(
                model=settings.compatible_model,
                messages=[
                    {"role": "user", "content": _TEXT_REVIEW_PROMPT},
                    {"role": "user", "content": f"待审核内容：\n{content[:1000]}"},
                ],
                max_tokens=150, temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            result = _extract_json(raw)
            if result.get("passed") is False:
                score = result.get("score")
                try:
                    score = float(score) if score is not None else None
                except (TypeError, ValueError):
                    score = None
                await _add_record(target_type, target_id, "ai", score, result.get("reason", ""))
        logger.info(f"[审核] 后台复查完成: {target_type}#{target_id}（图{len(image_urls or [])}张，文本{'已复查' if content else '无'}）")
    except Exception as e:
        logger.warning(f"[审核] 后台复查任务异常 ({target_type}#{target_id}): {e}")
