"""
天气查询相关 Pydantic 数据模型
"""
from typing import Optional
from pydantic import BaseModel, Field


class WeatherQueryRequest(BaseModel):
    """天气查询请求"""
    location: str = Field(..., min_length=1, description="徒步地点名称，如'武功山'")
    date: Optional[str] = Field(default=None, description="查询日期 (YYYY-MM-DD)，默认为今天")
    forecast_days: int = Field(default=7, ge=1, le=7, description="预报天数，最多7天")


class WeatherData(BaseModel):
    """天气数据"""
    date: str = Field(default="", description="日期")
    temperature: str = Field(default="", description="温度，如'18°C ~ 25°C'")
    precipitation: str = Field(default="", description="降水概率")
    wind: str = Field(default="", description="风力风向")
    uv_index: str = Field(default="", description="紫外线强度")
    alert: str = Field(default="", description="天气预警信息")


class WeatherResult(BaseModel):
    """天气查询结果"""
    location: str = Field(description="查询地点")
    forecast: list[WeatherData] = Field(default_factory=list, description="天气预报列表")
    hiking_assessment: str = Field(default="", description="徒步出行可行性评估")
    equipment_advice: str = Field(default="", description="天气对应的装备调整建议")