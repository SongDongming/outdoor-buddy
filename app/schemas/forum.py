"""
论坛 Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


class ForumCategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    sort_order: int
    created_at: datetime
    class Config: from_attributes = True


class ForumReplyOut(BaseModel):
    id: int
    content: str
    post_id: int
    author_id: int
    author_name: Optional[str] = None
    author_avatar_url: Optional[str] = None
    images: List[str] = []
    parent_id: Optional[int] = None
    reply_to_name: Optional[str] = None
    like_count: int = 0
    liked: bool = False
    is_hidden: bool = False
    created_at: datetime
    class Config: from_attributes = True


class ForumPostOut(BaseModel):
    id: int
    title: str
    content: str
    category_id: int
    category_name: Optional[str] = None
    author_id: int
    author_name: Optional[str] = None
    images: List[str] = []
    view_count: int
    reply_count: int
    like_count: int = 0
    liked: bool = False
    is_pinned: bool
    is_hidden: bool = False
    created_at: datetime
    updated_at: datetime
    replies: List[ForumReplyOut] = []
    class Config: from_attributes = True


class ForumPostListItem(BaseModel):
    """列表用 — 不含 replies 避免懒加载问题"""
    id: int
    title: str
    content: str
    category_id: int
    category_name: Optional[str] = None
    author_id: int
    author_name: Optional[str] = None
    images: List[str] = []
    view_count: int
    reply_count: int
    like_count: int = 0
    liked: bool = False
    is_pinned: bool
    is_hidden: bool = False
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes = True


class ForumPostListOut(BaseModel):
    posts: List[ForumPostOut]
    total: int
    page: int
    page_size: int


def _validate_image_urls(v: List[str]) -> List[str]:
    """图片 URL 白名单：仅接受本站上传路径 /static/img/uploads/，防外链/SSRF"""
    if not v:
        return v
    if len(v) > 9:
        raise ValueError("图片数量不能超过9张")
    clean = []
    for url in v:
        if not isinstance(url, str) or not url.startswith("/static/img/"):
            raise ValueError("仅支持本站上传的图片")
        if ".." in url.split("/"):
            raise ValueError("非法的图片路径")
        clean.append(url)
    return clean


class ForumPostCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(..., min_length=1, max_length=20000)
    category_id: int
    images: List[str] = []
    _v_images = field_validator("images")(_validate_image_urls)


class ForumReplyCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=20000)
    images: List[str] = []
    parent_id: Optional[int] = Field(default=None, description="父回复 ID（嵌套回复时指定，顶层回复为空）")
    _v_images = field_validator("images")(_validate_image_urls)


class ForumCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="分类名称")
    slug: Optional[str] = Field(default=None, max_length=50, description="唯一标识，不传则自动生成")
    description: Optional[str] = Field(default=None, max_length=200)