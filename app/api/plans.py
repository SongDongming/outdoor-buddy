"""预案 API — PlanAgent"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user
from app.schemas.plan import PlanGenerateRequest, PlanUpdateRequest
from app.schemas.common import ApiResponse
from app.agents.plan_agent import get_plan_agent
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/plans", tags=["行程预案"])


@router.post("/generate", response_model=ApiResponse)
async def generate_plan_api(req: PlanGenerateRequest, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """生成行程预案"""
    has_weather = bool(req.weather_data and req.weather_data.get('forecast'))
    print(f"[PLAN] 生成: days={req.route_params.get('days','?')}, altitude={req.route_params.get('max_altitude','?')}, weather={'有' if has_weather else '无'}")
    if not req.route_params:
        raise HTTPException(status_code=400, detail="请提供路线参数")
    try:
        agent = get_plan_agent()
        result = await agent.run(req.route_params, req.weather_data, req.user_params, req.ticket_data)
        return ApiResponse(code=200, message="预案生成成功", data=result)
    except Exception as e:
        logger.error(f"预案生成异常: {e}")
        raise HTTPException(status_code=500, detail="预案生成失败")


@router.post("/regenerate", response_model=ApiResponse)
async def regenerate_plan_api(req: PlanUpdateRequest, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """更新预案"""
    try:
        agent = get_plan_agent()
        result = await agent.run(req.route_params or {}, req.weather_data, req.user_params)
        return ApiResponse(code=200, message="预案更新成功", data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail="预案更新失败")