"""
装备缓存模型定义
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func
from app.models.database import Base


class EquipmentCache(Base):
    __tablename__ = "equipment_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String(200), nullable=False, index=True)
    category = Column(String(50), nullable=True, index=True)
    equipment_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)