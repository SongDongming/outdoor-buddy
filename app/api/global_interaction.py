"""全局交互 API — SupervisorAgent"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user
from app.schemas.common import ApiResponse
from app.agents.supervisor import get_supervisor_agent
from app.services.session_service import get_session_context, update_session_context, get_session_query_results, clear_session
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/interact", tags=["全局交互"])


@router.post("/parse", response_model=ApiResponse)
async def parse_user_intent(request: Request, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """自然语言指令解析 — SupervisorAgent"""
    body = await request.json()
    user_message = body.get("message", "")
    session_id = body.get("session_id", request.headers.get("X-Session-Id", "default"))

    if not user_message:
        return ApiResponse(code=400, message="请输入指令", data=None)

    context = await get_session_context(session_id, db)
    query_results = get_session_query_results(session_id)

    try:
        agent = get_supervisor_agent()
        result = await agent.run(user_message, {"context": context, "query_results": query_results})
    except Exception as e:
        logger.error(f"指令解析失败: {e}")
        return ApiResponse(code=500, message="指令解析失败", data={"response": "抱歉，请换个方式描述。"})

    return ApiResponse(code=200, message="success", data=result)


@router.get("/context/{session_id}", response_model=ApiResponse)
async def get_context(session_id: str, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    context = await get_session_context(session_id, db)
    return ApiResponse(code=200, message="success", data={"session_id": session_id, "context": context, "query_results": get_session_query_results(session_id)})


@router.delete("/context/{session_id}", response_model=ApiResponse)
async def clear_context_api(session_id: str, current_user: User | None = Depends(get_optional_user)):
    clear_session(session_id)
    return ApiResponse(code=200, message="会话已清除", data=None)