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
    author_avatar_url: Optional[str] = None
    images: List[str] = []
    parent_id: Optional[int] = None
    reply_to_name: Optional[str] = None
    like_count: int = 0
    liked: bool = False
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
    parent_id: Optional[int] = Field(default=None, description="父回复 ID（嵌套回复时指定，顶层回复为空）")


class ForumCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="分类名称")
    slug: Optional[str] = Field(default=None, max_length=50, description="唯一标识，不传则自动生成")
    description: Optional[str] = Field(default=None, max_length=200)