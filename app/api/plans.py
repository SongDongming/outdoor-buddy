"""预案 API — PlanAgent"""
import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user, rate_limited
from app.schemas.plan import PlanGenerateRequest, PlanUpdateRequest
from app.schemas.common import ApiResponse
from app.agents.plan_agent import get_plan_agent
from app.utils.logger import logger

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}

router = APIRouter(prefix="/api/v1/plans", tags=["行程预案"])


@router.post("/generate", response_model=ApiResponse)
async def generate_plan_api(req: PlanGenerateRequest, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user), _rl: None = Depends(rate_limited(10, 60))):
    """生成行程预案（支持 SSE 流式输出，逐段返回）"""
    has_weather = bool(req.weather_data and req.weather_data.get('forecast'))
    print(f"[PLAN] 生成: days={req.route_params.get('days','?')}, altitude={req.route_params.get('max_altitude','?')}, weather={'有' if has_weather else '无'}, stream={req.stream}")
    if not req.route_params:
        raise HTTPException(status_code=400, detail="请提供路线参数")

    # SSE 流式模式
    if req.stream:
        return StreamingResponse(
            _plan_stream(req),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    try:
        agent = get_plan_agent()
        result = await agent.run(req.route_params, req.weather_data, req.user_params, req.ticket_data)
        return ApiResponse(code=200, message="预案生成成功", data=result)
    except Exception as e:
        logger.error(f"预案生成异常: {e}")
        raise HTTPException(status_code=500, detail="预案生成失败")


async def _plan_stream(req: PlanGenerateRequest):
    """预案 SSE 流式生成器"""
    try:
        agent = get_plan_agent()
        async for ev in agent.stream_run(req.route_params, req.weather_data, req.user_params, req.ticket_data):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield 'data: {"type":"done"}\n\n'
    except Exception as e:
        logger.error(f"预案流式异常: {e}")
        yield 'data: {"type":"error","message":"预案生成失败"}\n\n'


@router.post("/regenerate", response_model=ApiResponse)
async def regenerate_plan_api(req: PlanUpdateRequest, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """更新预案"""
    try:
        agent = get_plan_agent()
        result = await agent.run(req.route_params or {}, req.weather_data, req.user_params)
        return ApiResponse(code=200, message="预案更新成功", data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail="预案更新失败")