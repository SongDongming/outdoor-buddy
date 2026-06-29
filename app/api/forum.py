"""
论坛 API 路由
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from app.models.database import get_db
from app.models.user import User
from app.models.forum import ForumCategory, ForumPost, ForumReply
from app.api.dependencies import get_current_user, get_optional_user
from app.schemas.forum import (
    ForumCategoryOut, ForumPostOut, ForumPostListItem, ForumPostListOut, ForumPostCreate,
    ForumReplyOut, ForumReplyCreate,
)
from app.schemas.common import ApiResponse
from app.utils.logger import logger
from app.services.storage_service import get_storage

router = APIRouter(prefix="/api/v1/forum", tags=["论坛"])


# ====== 分类 ======
DEFAULT_CATEGORIES = [
    ("路线讨论", "route-discussion", "讨论徒步路线、攻略、经验", 1),
    ("装备交流", "equipment-exchange", "装备评测、推荐、使用心得", 2),
    ("经验分享", "experience-sharing", "户外经验、技巧、心得分享", 3),
    ("约伴出行", "trip-partners", "寻找同伴、组队出行", 4),
    ("其他", "other", "其他户外相关话题", 5),
]

@router.get("/categories", response_model=ApiResponse)
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ForumCategory).order_by(ForumCategory.sort_order))
    cats = result.scalars().all()
    # 数据库为空时自动播种默认分类
    if not cats:
        for name, slug, desc, order in DEFAULT_CATEGORIES:
            db.add(ForumCategory(name=name, slug=slug, description=desc, sort_order=order))
        await db.commit()
        result = await db.execute(select(ForumCategory).order_by(ForumCategory.sort_order))
        cats = result.scalars().all()
    return ApiResponse(code=200, message="success", data=[
        ForumCategoryOut.model_validate(c).model_dump() for c in cats
    ])


# ====== 帖子列表 ======
@router.get("/posts", response_model=ApiResponse)
async def list_posts(
    category_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    query = select(ForumPost).options(selectinload(ForumPost.author), selectinload(ForumPost.category))
    count_q = select(func.count(ForumPost.id))
    if category_id:
        query = query.where(ForumPost.category_id == category_id)
        count_q = count_q.where(ForumPost.category_id == category_id)

    total = (await db.execute(count_q)).scalar() or 0
    query = query.order_by(desc(ForumPost.is_pinned), desc(ForumPost.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    posts = result.scalars().all()

    # 批量获取每个帖子的首条回复
    post_ids = [p.id for p in posts]
    latest_replies = {}
    if post_ids:
        from sqlalchemy import distinct, and_
        # 每个帖子取最新一条回复
        subq = (
            select(ForumReply.post_id, func.max(ForumReply.created_at).label("max_ts"))
            .where(ForumReply.post_id.in_(post_ids))
            .group_by(ForumReply.post_id)
            .subquery()
        )
        reply_query = (
            select(ForumReply)
            .options(selectinload(ForumReply.author))
            .join(subq, and_(ForumReply.post_id == subq.c.post_id, ForumReply.created_at == subq.c.max_ts))
        )
        reply_result = await db.execute(reply_query)
        for r in reply_result.scalars().all():
            latest_replies[r.post_id] = {
                "id": r.id, "content": r.content, "images": r.images or [],
                "author_name": r.author.username if r.author else "未知",
                "author_avatar_url": r.author.avatar_url if r.author else None,
                "created_at": str(r.created_at),
            }

    post_list = []
    for p in posts:
        d = ForumPostListItem.model_validate(p).model_dump()
        d["author_name"] = p.author.username if p.author else "未知"
        d["author_avatar_url"] = p.author.avatar_url if p.author else None
        d["category_name"] = p.category.name if p.category else "未分类"
        d["latest_reply"] = latest_replies.get(p.id)
        post_list.append(d)

    return ApiResponse(code=200, message="success", data={
        "posts": post_list, "total": total, "page": page, "page_size": page_size
    })


# ====== 帖子详情 ======
@router.get("/posts/{post_id}", response_model=ApiResponse)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    result = await db.execute(select(ForumPost).options(selectinload(ForumPost.author), selectinload(ForumPost.category), selectinload(ForumPost.replies).selectinload(ForumReply.author)).where(ForumPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    post.view_count = (post.view_count or 0) + 1
    await db.commit()
    await db.refresh(post)

    d = ForumPostOut.model_validate(post).model_dump()
    d["author_name"] = post.author.username if post.author else "未知"
    d["author_avatar_url"] = post.author.avatar_url if post.author else None
    d["category_name"] = post.category.name if post.category else "未分类"
    d["replies"] = []
    for r in post.replies:
        rd = ForumReplyOut.model_validate(r).model_dump()
        rd["author_name"] = r.author.username if r.author else "未知"
        rd["author_avatar_url"] = r.author.avatar_url if r.author else None
        d["replies"].append(rd)

    return ApiResponse(code=200, message="success", data=d)


# ====== 发帖 ======
@router.post("/posts", response_model=ApiResponse, status_code=201)
async def create_post(
    req: ForumPostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = ForumPost(
        title=req.title, content=req.content, category_id=req.category_id,
        author_id=current_user.id, images=req.images
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    # 查询分类名，避免懒加载
    cat_result = await db.execute(select(ForumCategory).where(ForumCategory.id == req.category_id))
    cat = cat_result.scalar_one_or_none()
    d = ForumPostListItem.model_validate(post).model_dump()
    d["author_name"] = current_user.username
    d["author_avatar_url"] = current_user.avatar_url
    d["category_name"] = cat.name if cat else "未分类"
    return ApiResponse(code=201, message="发帖成功", data=d)


# ====== 回复 ======
@router.post("/posts/{post_id}/replies", response_model=ApiResponse, status_code=201)
async def create_reply(
    post_id: int,
    req: ForumReplyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ForumPost).options(selectinload(ForumPost.author), selectinload(ForumPost.category), selectinload(ForumPost.replies).selectinload(ForumReply.author)).where(ForumPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")

    reply = ForumReply(
        content=req.content, post_id=post_id, author_id=current_user.id, images=req.images
    )
    db.add(reply)
    post.reply_count = (post.reply_count or 0) + 1
    await db.commit()
    await db.refresh(reply)
    d = ForumReplyOut.model_validate(reply).model_dump()
    d["author_name"] = current_user.username
    return ApiResponse(code=201, message="回复成功", data=d)


# ====== 获取帖子回复列表 ======
@router.get("/posts/{post_id}/replies", response_model=ApiResponse)
async def get_replies(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    result = await db.execute(
        select(ForumReply)
        .options(selectinload(ForumReply.author))
        .where(ForumReply.post_id == post_id)
        .order_by(ForumReply.created_at)
    )
    replies = result.scalars().all()
    reply_list = []
    for r in replies:
        d = ForumReplyOut.model_validate(r).model_dump()
        d["author_name"] = r.author.username if r.author else "未知"
        d["author_avatar_url"] = r.author.avatar_url if r.author else None
        reply_list.append(d)
    return ApiResponse(code=200, message="success", data={"replies": reply_list})


# ====== 删除帖子 ======
@router.delete("/posts/{post_id}", response_model=ApiResponse)
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ForumPost).where(ForumPost.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if post.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权删除")

    # 清理帖子及其回复的所有图片文件
    storage = get_storage()
    delete_errors = []

    # 清理帖子图片
    if post.images:
        for img_url in post.images:
            try:
                await storage.delete_by_url(img_url)
            except Exception as e:
                delete_errors.append(img_url)
                logger.warning(f"删除帖子图片失败: {img_url} — {e}")

    # 清理帖子下的所有回复图片
    replies_result = await db.execute(
        select(ForumReply).where(ForumReply.post_id == post_id)
    )
    replies = replies_result.scalars().all()
    for reply in replies:
        if reply.images:
            for img_url in reply.images:
                try:
                    await storage.delete_by_url(img_url)
                except Exception as e:
                    delete_errors.append(img_url)
                    logger.warning(f"删除回复图片失败: {img_url} — {e}")

    if delete_errors:
        logger.warning(f"部分文件清理失败 ({len(delete_errors)} 个)，帖子将继续删除")

    await db.delete(post)
    await db.commit()
    return ApiResponse(code=200, message="删除成功", data=None)


# ====== 删除回复 ======
@router.delete("/replies/{reply_id}", response_model=ApiResponse)
async def delete_reply(
    reply_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(ForumReply).where(ForumReply.id == reply_id))
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="回复不存在")
    if reply.author_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权删除")

    # 清理回复中的图片文件
    storage = get_storage()
    if reply.images:
        for img_url in reply.images:
            try:
                await storage.delete_by_url(img_url)
            except Exception as e:
                logger.warning(f"删除回复图片失败: {img_url} — {e}")

    # 更新帖子的回复计数
    post_result = await db.execute(select(ForumPost).where(ForumPost.id == reply.post_id))
    post = post_result.scalar_one_or_none()
    if post:
        post.reply_count = max(0, (post.reply_count or 0) - 1)

    await db.delete(reply)
    await db.commit()
    return ApiResponse(code=200, message="删除成功", data=None)


# ====== 图片上传 ======
@router.post("/upload", response_model=ApiResponse)
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过5MB")
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/gif/webp 格式")

    content = await file.read()
    filename = f"{uuid.uuid4().hex}.{ext}"
    storage = get_storage()
    try:
        url = await storage.save(content, "uploads", filename)
    except Exception as e:
        logger.error(f"论坛图片保存失败: {e}")
        raise HTTPException(status_code=503, detail="存储服务暂时不可用，请稍后重试")

    return ApiResponse(code=200, message="上传成功", data={"url": url})