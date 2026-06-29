"""天气 API — WeatherAgent"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user
from app.schemas.weather import WeatherQueryRequest
from app.schemas.common import ApiResponse
from app.agents.weather_agent import get_weather_agent
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/weather", tags=["天气查询"])


@router.post("/query", response_model=ApiResponse)
async def query_weather_api(req: WeatherQueryRequest, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """查询天气"""
    print(f"[WEATHER] 查询: {req.location}")
    try:
        agent = get_weather_agent()
        result = await agent.run(req.location, req.date, req.forecast_days)
        return ApiResponse(code=200, message="success", data=result)
    except Exception as e:
        logger.error(f"天气查询异常: {e}")
        raise HTTPException(status_code=500, detail="天气查询服务暂时不可用")


@router.get("/quick/{location}", response_model=ApiResponse)
async def quick_weather(location: str, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """快速天气"""
    try:
        agent = get_weather_agent()
        result = await agent.run(location, None, 1)
        return ApiResponse(code=200, message="success", data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail="天气查询服务暂时不可用")