"""
论坛 Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field
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
    images: List[str] = []
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
    is_pinned: bool
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
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes = True


class ForumPostListOut(BaseModel):
    posts: List[ForumPostOut]
    total: int
    page: int
    page_size: int


class ForumPostCreate(BaseModel):
    title: str = Field(default="", max_length=200)
    content: str = Field(..., min_length=1)
    category_id: int
    images: List[str] = []


class ForumReplyCreate(BaseModel):
    content: str = Field(..., min_length=1)
    images: List[str] = []