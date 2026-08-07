"""
行程预案相关 Pydantic 数据模型
"""
from typing import Optional
from pydantic import BaseModel, Field


class PlanGenerateRequest(BaseModel):
    """行程预案生成请求"""
    route_params: dict = Field(default_factory=dict, description="路线参数（天数、海拔、难度、地形等）")
    weather_data: Optional[dict] = Field(default=None, description="天气数据")
    ticket_data: Optional[dict] = Field(default=None, description="交通票务数据")
    user_params: Optional[dict] = Field(default=None, description="用户个性化参数")
    stream: bool = Field(default=False, description="是否 SSE 流式输出")


class PlanGenerateResult(BaseModel):
    """行程预案生成结果"""
    altitude_plan: str = Field(default="", description="海拔健康应对方案")
    fitness_plan: str = Field(default="", description="体能与行程分配建议")
    weather_risk_plan: str = Field(default="", description="天气风险应对预案")
    environment_knowledge: str = Field(default="", description="环境安全知识推送")
    daily_guide: str = Field(default="", description="每日行动指南")
    transportation_plan: str = Field(default="", description="交通出行建议")


class PlanUpdateRequest(BaseModel):
    """预案参数更新请求"""
    plan_id: Optional[int] = Field(default=None, description="已有预案ID")
    route_params: Optional[dict] = Field(default=None, description="更新后的路线参数")
    weather_data: Optional[dict] = Field(default=None, description="更新后的天气数据")
    user_params: Optional[dict] = Field(default=None, description="更新后的用户参数")