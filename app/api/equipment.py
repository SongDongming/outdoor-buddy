"""
装备 API 路由 — 对接 EquipmentAgent
"""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user, rate_limited
from app.schemas.equipment import EquipmentQueryRequest, EquipmentRecommendRequest, EQUIPMENT_CATEGORIES
from app.schemas.common import ApiResponse
from app.agents.equipment_agent import get_equipment_agent
from app.utils.logger import logger

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}

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
async def recommend_equipment_api(req: EquipmentRecommendRequest, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user), _rl: None = Depends(rate_limited(10, 60))):
    """装备推荐（支持 SSE 流式输出）"""
    print(f"[EQUIP] 推荐: mode={req.mode}, days={req.days}, season={req.season}, stream={req.stream}")
    params = {
        "mode": req.mode, "days": req.days, "season": req.season,
        "terrain": req.terrain, "people_count": req.people_count,
    }

    # SSE 流式模式
    if req.stream:
        return StreamingResponse(
            _equipment_stream(params),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    try:
        agent = get_equipment_agent()
        result = await agent.run(params)
        return ApiResponse(code=200, message="success", data=result)
    except Exception as e:
        logger.error(f"装备推荐异常: {e}")
        raise HTTPException(status_code=500, detail="装备推荐服务暂时不可用")


async def _equipment_stream(params: dict):
    """装备推荐 SSE 流式生成器"""
    try:
        agent = get_equipment_agent()
        async for ev in agent.stream_run(params):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield 'data: {"type":"done"}\n\n'
    except Exception as e:
        logger.error(f"装备推荐流式异常: {e}")
        yield 'data: {"type":"error","message":"装备推荐服务暂时不可用"}\n\n'


@router.get("/categories", response_model=ApiResponse)
async def get_categories():
    return ApiResponse(code=200, message="success", data={"categories": EQUIPMENT_CATEGORIES})