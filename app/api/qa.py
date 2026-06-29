"""
问答 API 路由 — 对接 QAAgent
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user
from app.schemas.common import ApiResponse
from app.agents.qa_agent import get_qa_agent
from app.services.session_service import get_session_context, update_session_context
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/qa", tags=["专业知识问答"])


@router.post("/chat", response_model=ApiResponse)
async def qa_chat_api(request: Request, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """专业知识问答 — LangGraph QAAgent"""
    body = await request.json()
    user_message = body.get("message", "")
    session_id = body.get("session_id", request.headers.get("X-Session-Id", "default"))

    if not user_message:
        return ApiResponse(code=400, message="请输入问题", data=None)

    print(f"[QA] 问题: {user_message[:60]}...")
    context = await get_session_context(session_id, db)

    try:
        agent = get_qa_agent()
        result = await agent.run(user_message, context)
    except Exception as e:
        logger.error(f"问答异常: {e}")
        return ApiResponse(code=500, message="问答服务暂时不可用", data=None)

    # 更新会话上下文
    context.append({"role": "user", "content": user_message})
    context.append({"role": "assistant", "content": result["answer"]})
    await update_session_context(session_id, context, current_user.id if current_user else None, db)

    answer = result["answer"]
    if result.get("safety_warning"):
        answer += f"\n\n⚠️ {result['safety_warning']}"

    return ApiResponse(code=200, message="success", data={"answer": answer, "session_id": session_id})