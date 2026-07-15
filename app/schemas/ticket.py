"""
交通票务相关 Pydantic 数据模型
"""
from typing import Optional
from pydantic import BaseModel, Field


class TicketQueryRequest(BaseModel):
    """票务查询请求"""
    from_city: str = Field(..., min_length=1, description="出发城市，如'北京'")
    to_city: str = Field(..., min_length=1, description="目的城市，如'萍乡'")
    date: str = Field(..., description="出行日期 (YYYY-MM-DD)")


class TicketInfo(BaseModel):
    """单条车次信息"""
    train_no: str = Field(default="", description="车次编号")
    departure_time: str = Field(default="", description="出发时间")
    arrival_time: str = Field(default="", description="到达时间")
    duration: str = Field(default="", description="历时")
    seat_types: str = Field(default="", description="座位类型与票价")
    status: str = Field(default="", description="余票状态")


class TicketResult(BaseModel):
    """票务查询结果"""
    from_city: str = Field(description="出发城市")
    to_city: str = Field(description="目的城市")
    date: str = Field(description="出行日期")
    tickets: list[TicketInfo] = Field(default_factory=list, description="车次列表")
    transfer_advice: str = Field(default="", description="到站接驳建议")
    travel_time_advice: str = Field(default="", description="推荐出行时段")
    error_msg: str = Field(default="", description="错误信息，查询失败时返回")