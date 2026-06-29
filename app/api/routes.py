"""
路线查询 API 路由 — 对接 RouteAgent
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user
from app.schemas.route import RouteSearchRequest
from app.schemas.common import ApiResponse
from app.agents.route_agent import get_route_agent
from app.services.route_service import _get_cached_route, _cache_route
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/routes", tags=["路线查询"])


@router.post("/search", response_model=ApiResponse)
async def search_routes_api(
    req: RouteSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """搜索徒步路线 — LangGraph RouteAgent"""
    print(f"[ROUTE] 搜索: {req.keyword}")
    logger.info(f"路线搜索: {req.keyword}")

    # 检查缓存
    cached = await _get_cached_route(req.keyword, db)
    if cached:
        return ApiResponse(code=200, message="success (cached)", data=cached)

    try:
        agent = get_route_agent()
        result = await agent.run(req.keyword)
    except Exception as e:
        import traceback
        print(f"[ROUTE] 搜索异常: {e}", flush=True)
        logger.error(f"路线搜索异常: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="路线查询服务暂时不可用")

    # 写入缓存
    await _cache_route(req.keyword, result, db)

    return ApiResponse(code=200, message="success", data=result)