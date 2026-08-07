"""
问答 API 路由 — 对接 QAAgent
"""
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_optional_user, rate_limited
from app.schemas.common import ApiResponse
from app.agents.qa_agent import get_qa_agent
from app.services.session_service import get_session_context, update_session_context
from app.utils.logger import logger

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

router = APIRouter(prefix="/api/v1/qa", tags=["专业知识问答"])


@router.post("/chat", response_model=ApiResponse)
async def qa_chat_api(request: Request, db: AsyncSession = Depends(get_db), current_user: User | None = Depends(get_optional_user), _rl: None = Depends(rate_limited(10, 60))):
    """专业知识问答 — LangGraph QAAgent（支持 SSE 流式输出）"""
    body = await request.json()
    user_message = body.get("message", "")
    session_id = body.get("session_id", request.headers.get("X-Session-Id", "default"))
    stream = bool(body.get("stream", False))

    if not user_message:
        return ApiResponse(code=400, message="请输入问题", data=None)

    print(f"[QA] 问题: {user_message[:60]}...")
    context = await get_session_context(session_id, db)

    # SSE 流式模式
    if stream:
        user_id = current_user.id if current_user else None
        return StreamingResponse(
            _qa_stream(user_message, session_id, context, user_id, db),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

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


async def _qa_stream(user_message: str, session_id: str, context: list, user_id: int | None, db: AsyncSession):
    """QA SSE 流式生成器：逐 token 推送，流完后更新会话上下文"""
    full = ""
    try:
        agent = get_qa_agent()
        async for chunk in agent.stream_run(user_message, context):
            full += chunk
            yield _sse({"type": "token", "content": chunk})

        # 流完后更新会话上下文
        new_context = context + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": full},
        ]
        await update_session_context(session_id, new_context, user_id, db)

        yield _sse({"type": "done", "content": full})
    except Exception as e:
        logger.error(f"问答流式异常: {e}")
        yield _sse({"type": "error", "message": "问答服务暂时不可用"})