"""
用户模型定义
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.models.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    email_verified = Column(Boolean, default=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")
    avatar_url = Column(String(500), nullable=True)
    is_banned = Column(Boolean, default=False)  # 内容审核封禁
    banned_until = Column(DateTime(timezone=True), nullable=True)
    violation_count = Column(Integer, default=0)  # 累计违规次数
    reset_token = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())