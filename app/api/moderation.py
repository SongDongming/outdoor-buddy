"""
内容审核 API — 用户举报 + 管理员审核中心
- POST /report          用户举报帖子/回复/头像（限流防刷）
- GET  /queue           admin 待审队列（举报 + AI/NSFW 标记）
- POST /resolve/{id}    admin 处理：hide / delete / ignore，可同时封禁用户
"""
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database import get_db
from app.models.user import User
from app.models.forum import ForumPost, ForumReply
from app.models.moderation import ModerationRecord
from app.api.dependencies import get_current_admin, get_current_user, rate_limited
from app.schemas.common import ApiResponse
from app.utils.logger import logger
from app.services.storage_service import get_storage

router = APIRouter(prefix="/api/v1/moderation", tags=["内容审核"])

VALID_TARGETS = ("post", "reply", "avatar")
VALID_ACTIONS = ("hide", "delete", "ignore")
ACTION_TO_STATUS = {"hide": "resolved_hidden", "delete": "resolved_deleted", "ignore": "resolved_ignored"}


def _now() -> datetime:
    """naive UTC 时间（reviewed_at 列为 TIMESTAMP WITHOUT TIME ZONE）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ReportRequest(BaseModel):
    target_type: str = Field(..., description="post/reply/avatar")
    target_id: int
    reason: str = Field(..., max_length=50, description="举报原因")
    note: str = Field(default="", max_length=500, description="补充说明")


class ResolveRequest(BaseModel):
    action: str = Field(..., description="hide/delete/ignore")
    ban_user: bool = Field(default=False, description="是否同时封禁目标作者")


# ==============================
# 举报
# ==============================

@router.post("/report", response_model=ApiResponse)
async def create_report(
    req: ReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rate: None = Depends(rate_limited(5, 600)),
):
    """用户举报帖子/回复/头像（每用户 10 分钟最多 5 次）"""
    if req.target_type not in VALID_TARGETS:
        raise HTTPException(status_code=400, detail="无效的举报类型")

    if req.target_type == "post":
        exists = await db.get(ForumPost, req.target_id)
    elif req.target_type == "reply":
        exists = await db.get(ForumReply, req.target_id)
    else:
        exists = await db.get(User, req.target_id)
    if not exists:
        raise HTTPException(status_code=404, detail="举报目标不存在")

    rec = ModerationRecord(
        target_type=req.target_type,
        target_id=req.target_id,
        reporter_id=current_user.id,
        report_reason=req.reason,
        report_note=req.note.strip() or None,
        source="report",
        status="pending",
    )
    db.add(rec)
    await db.commit()
    logger.info(f"[审核] 用户#{current_user.id} 举报 {req.target_type}#{req.target_id}: {req.reason}")
    return ApiResponse(code=200, message="举报成功，管理员将尽快处理", data={"record_id": rec.id})


# ==============================
# 管理员审核队列
# ==============================

async def _load_target(db: AsyncSession, rec: ModerationRecord) -> Optional[dict]:
    """加载被审目标的内容预览（附作者信息），用于管理员直接审阅"""
    if rec.target_type == "post":
        result = await db.execute(
            select(ForumPost).options(selectinload(ForumPost.author)).where(ForumPost.id == rec.target_id)
        )
        post = result.scalar_one_or_none()
        if not post:
            return None
        return {
            "id": post.id, "kind": "post", "title": post.title,
            "content": post.content, "images": post.images or [],
            "author_id": post.author_id,
            "author_name": post.author.username if post.author else "未知",
            "is_hidden": bool(post.is_hidden),
        }
    if rec.target_type == "reply":
        result = await db.execute(
            select(ForumReply).options(selectinload(ForumReply.author)).where(ForumReply.id == rec.target_id)
        )
        reply = result.scalar_one_or_none()
        if not reply:
            return None
        return {
            "id": reply.id, "kind": "reply",
            "content": reply.content, "images": reply.images or [],
            "post_id": reply.post_id, "author_id": reply.author_id,
            "author_name": reply.author.username if reply.author else "未知",
            "is_hidden": bool(reply.is_hidden),
        }
    # avatar
    user = await db.get(User, rec.target_id)
    if not user:
        return None
    return {
        "id": user.id, "kind": "avatar", "username": user.username,
        "avatar_url": user.avatar_url, "is_banned": bool(user.is_banned),
        "violation_count": user.violation_count or 0,
    }


@router.get("/queue", response_model=ApiResponse)
async def moderation_queue(
    status: str = Query("pending", description="pending / all / resolved_*"),
    target_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """管理员审核队列"""
    query = select(ModerationRecord)
    count_q = select(func.count(ModerationRecord.id))
    if status and status != "all":
        query = query.where(ModerationRecord.status == status)
        count_q = count_q.where(ModerationRecord.status == status)
    if target_type:
        query = query.where(ModerationRecord.target_type == target_type)
        count_q = count_q.where(ModerationRecord.target_type == target_type)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(
        query.order_by(desc(ModerationRecord.created_at))
        .offset((page - 1) * page_size).limit(page_size)
    )
    records = result.scalars().all()

    items = []
    for rec in records:
        item = {
            "id": rec.id,
            "target_type": rec.target_type,
            "target_id": rec.target_id,
            "reporter_id": rec.reporter_id,
            "report_reason": rec.report_reason,
            "report_note": rec.report_note,
            "source": rec.source,
            "ai_score": rec.ai_score,
            "ai_reason": rec.ai_reason,
            "status": rec.status,
            "created_at": str(rec.created_at),
            "target": await _load_target(db, rec),
        }
        if rec.reporter_id:
            reporter = await db.get(User, rec.reporter_id)
            item["reporter_name"] = reporter.username if reporter else "未知"
        else:
            item["reporter_name"] = None
        items.append(item)

    return ApiResponse(code=200, message="success", data={"items": items, "total": total})


# ==============================
# 管理员处理
# ==============================

async def _delete_post_images(db: AsyncSession, post: ForumPost, storage) -> None:
    """删除帖子及其全部回复的图片文件"""
    result = await db.execute(select(ForumReply).where(ForumReply.post_id == post.id))
    replies = result.scalars().all()
    urls = list(post.images or [])
    for r in replies:
        urls.extend(r.images or [])
    for url in urls:
        try:
            await storage.delete_by_url(url)
        except Exception as e:
            logger.warning(f"[审核] 删除图片失败: {url} — {e}")


async def _delete_reply_tree(db: AsyncSession, reply: ForumReply, storage) -> int:
    """删除回复及其所有子孙回复（含图片），返回删除条数"""
    from app.api.forum import _collect_reply_ids
    reply_ids = await _collect_reply_ids(db, reply.id)
    result = await db.execute(select(ForumReply).where(ForumReply.id.in_(reply_ids)))
    all_replies = result.scalars().all()
    for r in all_replies:
        for url in (r.images or []):
            try:
                await storage.delete_by_url(url)
            except Exception as e:
                logger.warning(f"[审核] 删除回复图片失败: {url} — {e}")
        await db.delete(r)
    return len(reply_ids)


@router.post("/resolve/{record_id}", response_model=ApiResponse)
async def resolve_record(
    record_id: int,
    req: ResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """管理员处理一条审核记录：hide(隐藏) / delete(删除) / ignore(忽略)，可附带封禁作者"""
    rec = await db.get(ModerationRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")
    if req.action not in VALID_ACTIONS:
        raise HTTPException(status_code=400, detail="无效操作")

    storage = get_storage()
    target_author_id: Optional[int] = None

    if req.action == "hide":
        if rec.target_type == "post":
            post = await db.get(ForumPost, rec.target_id)
            if post:
                post.is_hidden = True
                target_author_id = post.author_id
        elif rec.target_type == "reply":
            reply = await db.get(ForumReply, rec.target_id)
            if reply:
                reply.is_hidden = True
                target_author_id = reply.author_id
        # avatar：隐藏不处理，删除头像用 delete

    elif req.action == "delete":
        if rec.target_type == "post":
            post = await db.get(ForumPost, rec.target_id)
            if post:
                target_author_id = post.author_id
                await _delete_post_images(db, post, storage)
                await db.delete(post)
                # 清理该帖相关的所有待审记录
                await _resolve_related_records(db, "post", post.id, "resolved_deleted", current_user.id)
        elif rec.target_type == "reply":
            reply = await db.get(ForumReply, rec.target_id)
            if reply:
                target_author_id = reply.author_id
                post_result = await db.execute(select(ForumPost).where(ForumPost.id == reply.post_id))
                post = post_result.scalar_one_or_none()
                deleted = await _delete_reply_tree(db, reply, storage)
                if post:
                    post.reply_count = max(0, (post.reply_count or 0) - deleted)
                await _resolve_related_records(db, "reply", reply.id, "resolved_deleted", current_user.id)
        elif rec.target_type == "avatar":
            user = await db.get(User, rec.target_id)
            if user:
                target_author_id = user.id
                if user.avatar_url:
                    try:
                        await storage.delete_by_url(user.avatar_url)
                    except Exception as e:
                        logger.warning(f"[审核] 删除头像文件失败: {e}")
                    user.avatar_url = None

    # 可选：封禁目标作者（含违规次数累计）
    if req.ban_user and target_author_id:
        target_user = await db.get(User, target_author_id)
        if target_user:
            target_user.is_banned = True
            target_user.banned_until = None  # 永久封禁（后续可扩展到期逻辑）
            target_user.violation_count = (target_user.violation_count or 0) + 1
            logger.info(f"[审核] 管理员#{current_user.id} 封禁用户#{target_user.id}")

    rec.status = ACTION_TO_STATUS.get(req.action, f"resolved_{req.action}")
    rec.reviewed_by = current_user.id
    rec.reviewed_at = _now()
    await db.commit()
    return ApiResponse(code=200, message="处理完成", data=None)


async def _resolve_related_records(db: AsyncSession, target_type: str, target_id: int, new_status: str, reviewer_id: int) -> None:
    """把指向同一目标的其它待审记录一并归档（防止删除后残留 pending）"""
    result = await db.execute(
        select(ModerationRecord).where(
            ModerationRecord.target_type == target_type,
            ModerationRecord.target_id == target_id,
            ModerationRecord.status == "pending",
        )
    )
    for r in result.scalars().all():
        r.status = new_status
        r.reviewed_by = reviewer_id
        r.reviewed_at = _now()
