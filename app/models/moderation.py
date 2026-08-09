"""
内容审核记录模型 — 举报 + AI/NSFW 标记统一进入审核队列
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, func
from app.models.database import Base


class ModerationRecord(Base):
    """一条待审核/已审核记录（用户举报 或 AI/NSFW 自动标记）"""
    __tablename__ = "moderation_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_type = Column(String(20), nullable=False, index=True)  # post / reply / avatar
    target_id = Column(Integer, nullable=False, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 举报人（AI 标记为空）
    report_reason = Column(String(50), nullable=True)   # 举报原因 或 ai_flagged / nsfw_flagged
    report_note = Column(Text, nullable=True)           # 举报补充说明
    source = Column(String(20), default="report")       # report / ai / nsfw
    ai_score = Column(Float, nullable=True)             # NSFW 概率 / AI 违规分数（快照）
    ai_reason = Column(String(200), nullable=True)      # 快照原因
    status = Column(String(20), default="pending", index=True)
    # pending / resolved_hidden / resolved_deleted / resolved_ignored
    reviewed_by = Column(Integer, nullable=True)        # 处理管理员 id
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
