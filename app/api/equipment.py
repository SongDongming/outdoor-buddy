"""
装备 API 路由 — 对接 EquipmentAgent
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user
from app.schemas.equipment import EquipmentQueryRequest, EquipmentRecommendRequest, EQUIPMENT_CATEGORIES
from app.schemas.common import ApiResponse
from app.agents.equipment_agent import get_equipment_agent
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/equipment", tags=["装备查询与推荐"])


@router.post("/search", response_model=ApiResponse)
async def search_equipment_api(req: EquipmentQueryRequest, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """装备查询"""
    try:
        agent = get_equipment_agent()
        result = await agent.run({"keyword": req.keyword, "category": req.category})
        return ApiResponse(code=200, message="success", data=result)
    except Exception as e:
        logger.error(f"装备查询异常: {e}")
        raise HTTPException(status_code=500, detail="装备查询服务暂时不可用")


@router.post("/recommend", response_model=ApiResponse)
async def recommend_equipment_api(req: EquipmentRecommendRequest, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """装备推荐"""
    print(f"[EQUIP] 推荐: mode={req.mode}, days={req.days}, season={req.season}")
    try:
        agent = get_equipment_agent()
        result = await agent.run({
            "mode": req.mode, "days": req.days, "season": req.season,
            "terrain": req.terrain, "people_count": req.people_count,
        })
        return ApiResponse(code=200, message="success", data=result)
    except Exception as e:
        logger.error(f"装备推荐异常: {e}")
        raise HTTPException(status_code=500, detail="装备推荐服务暂时不可用")


@router.get("/categories", response_model=ApiResponse)
async def get_categories():
    return ApiResponse(code=200, message="success", data={"categories": EQUIPMENT_CATEGORIES})