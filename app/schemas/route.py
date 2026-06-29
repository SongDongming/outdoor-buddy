"""
路线查询相关 Pydantic 数据模型
"""
from typing import Optional
from pydantic import BaseModel, Field


class RouteSearchRequest(BaseModel):
    """路线搜索请求"""
    keyword: str = Field(..., min_length=1, max_length=200, description="搜索关键词，如'武功山经典徒步路线'")


class RouteInfo(BaseModel):
    """单条路线信息"""
    name: str = Field(default="", description="路线名称")
    distance: str = Field(default="", description="全程距离")
    elevation_gain: str = Field(default="", description="累计爬升")
    max_altitude: str = Field(default="", description="最高海拔")
    difficulty: str = Field(default="", description="难度等级")
    duration: str = Field(default="", description="预计耗时")
    best_season: str = Field(default="", description="最佳出行季节")
    summary: str = Field(default="", description="路线轨迹概要")
    rating: str = Field(default="", description="用户评价")
    link: str = Field(default="", description="详情链接")


class RouteSearchResult(BaseModel):
    """路线搜索结果"""
    keyword: str = Field(description="搜索关键词")
    routes: list[RouteInfo] = Field(default_factory=list, description="路线列表")
    llm_summary: str = Field(default="", description="大模型生成的路线分析与注意事项")
    source: str = Field(default="2bulu", description="数据来源")