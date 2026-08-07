"""
论坛数据模型 — ForumCategory, ForumPost, ForumReply, ForumReplyLike
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON, func, UniqueConstraint
from sqlalchemy.orm import relationship
from app.models.database import Base
from app.models.user import User  # 确保 User 在 ForumPost 之前加载


class ForumCategory(Base):
    __tablename__ = "forum_categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    posts = relationship("ForumPost", back_populates="category")


class ForumPost(Base):
    __tablename__ = "forum_posts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    category_id = Column(Integer, ForeignKey("forum_categories.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    images = Column(JSON, default=[])
    view_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    category = relationship("ForumCategory", back_populates="posts")
    author = relationship("User")
    replies = relationship("ForumReply", back_populates="post", order_by="ForumReply.created_at")


class ForumReply(Base):
    __tablename__ = "forum_replies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    post_id = Column(Integer, ForeignKey("forum_posts.id", ondelete="CASCADE"))
    author_id = Column(Integer, ForeignKey("users.id"))
    images = Column(JSON, default=[])
    parent_id = Column(Integer, ForeignKey("forum_replies.id", ondelete="CASCADE"), nullable=True, default=None)
    like_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    post = relationship("ForumPost", back_populates="replies")
    author = relationship("User")
    parent = relationship("ForumReply", remote_side=[id], backref="children")


class ForumReplyLike(Base):
    """回复点赞记录（唯一约束: 同一用户对同一回复只点赞一次）"""
    __tablename__ = "forum_reply_likes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    reply_id = Column(Integer, ForeignKey("forum_replies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("reply_id", "user_id", name="uq_forum_reply_like"),)