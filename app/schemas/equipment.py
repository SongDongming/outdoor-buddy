"""
装备相关 Pydantic 数据模型
"""
from typing import Optional, List
from pydantic import BaseModel, Field


# 装备八大分类体系
EQUIPMENT_CATEGORIES = ["帐篷", "睡袋", "背包", "炊具", "服装", "鞋靴", "登山配件", "急救用品"]


class EquipmentQueryRequest(BaseModel):
    """装备查询请求"""
    keyword: str = Field(..., min_length=1, description="装备名称或分类关键词")
    category: Optional[str] = Field(default=None, description="装备分类")


class EquipmentItem(BaseModel):
    """单件装备信息"""
    name: str = Field(default="", description="装备名称")
    brand: str = Field(default="", description="品牌")
    model: str = Field(default="", description="型号")
    weight: str = Field(default="", description="重量")
    price: str = Field(default="", description="参考价格")
    scenario: str = Field(default="", description="适用场景")
    water_resistance: str = Field(default="", description="防水/保暖等级")
    rating: str = Field(default="", description="用户口碑")
    source: str = Field(default="", description="信息来源")


class EquipmentRecommendRequest(BaseModel):
    """装备推荐请求"""
    route_params: Optional[dict] = Field(default=None, description="路线参数（天数、难度、海拔、地形等）")
    mode: str = Field(default="light", description="徒步模式: light(轻装) / heavy(重装)")
    days: int = Field(default=1, ge=1, le=30, description="徒步天数")
    season: str = Field(default="春", description="出行季节")
    terrain: str = Field(default="山地", description="地形特征")
    people_count: int = Field(default=1, ge=1, le=20, description="出行人数")


class EquipmentRecommendResult(BaseModel):
    """装备推荐结果"""
    mode: str = Field(description="徒步模式")
    days: int = Field(description="徒步天数")
    equipment_list: list = Field(default_factory=list, description="分类装备清单")
    buying_advice: str = Field(default="", description="选购建议")
    price_range: str = Field(default="", description="参考价格区间")
    lightweight_alternatives: str = Field(default="", description="轻量化替代方案")