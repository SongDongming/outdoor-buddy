"""票务 API — 对接 12306 MCP 服务"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user
from app.schemas.ticket import TicketQueryRequest
from app.schemas.common import ApiResponse
from app.services.ticket_service import query_tickets
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/tickets", tags=["交通票务"])


@router.post("/query", response_model=ApiResponse)
async def query_tickets_api(req: TicketQueryRequest, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """查询火车票（通过 12306 MCP 服务）"""
    logger.info(f"[TICKET] 查询: {req.from_city} -> {req.to_city}, {req.date}")
    if not req.from_city or not req.to_city or not req.date:
        raise HTTPException(status_code=400, detail="请提供出发城市、目的城市和出行日期")
    try:
        result = await query_tickets(req.from_city, req.to_city, req.date)
        # 如果 MCP 查询失败且无结果，返回 503 提示服务不可用
        if result.get("error_msg") and not result.get("tickets"):
            return ApiResponse(code=503, message=result["error_msg"], data=result)
        return ApiResponse(code=200, message="success", data=result)
    except Exception as e:
        logger.error(f"票务查询异常: {e}")
        raise HTTPException(status_code=500, detail="票务查询服务暂时不可用")