"""
行程预案模型定义
"""
from sqlalchemy import Column, Integer, DateTime, JSON
from sqlalchemy.sql import func
from app.models.database import Base


class TripPlan(Base):
    __tablename__ = "trip_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    route_params = Column(JSON, nullable=True)
    weather_data = Column(JSON, nullable=True)
    plan_content = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())