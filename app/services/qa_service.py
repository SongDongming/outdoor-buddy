"""
专业知识问答服务模块
对话式AI问答，覆盖户外全场景专业知识，支持多轮上下文对话
"""
from app.utils.llm_client import llm_chat, llm_chat_stream
from app.utils.logger import logger

# 户外专业知识问答系统提示词
QA_SYSTEM_PROMPT = """你是户外徒步领域的资深专家，知识覆盖以下五大核心领域：
1. 野外生存技能：露营选址、取水净水、野外取火、方向辨别、绳索使用
2. 户外急救常识：骨折固定、失温处理、中暑急救、蛇虫咬伤、高原反应
3. 天气风险判断：云层识别、风速判断、雷雨预警、温差应对
4. LNT户外环保法则：垃圾处理、营地选择、野外如厕、用火规范
5. 装备使用保养：帐篷搭建、睡袋保养、冲锋衣清洗、登山杖使用

回答要求：
- 内容准确实用，基于户外专业知识
- 高危场景（高反、失温、雷击、野外遇险等）必须附带安全风险提示
- 使用中文回答，结构清晰
- 如果用户的问题超出户外知识范围，友好引导回户外话题"""


async def qa_chat(
    user_message: str,
    context: list[dict] | None = None,
) -> str:
    """
    专业知识问答（同步）
    Args:
        user_message: 用户问题
        context: 历史对话上下文
    Returns:
        AI 回答文本
    """
    messages = list(context or [])
    messages.append({"role": "user", "content": user_message})

    logger.info(f"知识问答: {user_message[:50]}...")

    return await llm_chat(
        messages=messages,
        system_prompt=QA_SYSTEM_PROMPT,
        temperature=0.7,
        max_tokens=2048,
    )


async def qa_chat_stream(
    user_message: str,
    context: list[dict] | None = None,
):
    """
    专业知识问答（流式）
    Args:
        user_message: 用户问题
        context: 历史对话上下文
    Yields:
        逐段返回的文本
    """
    messages = list(context or [])
    messages.append({"role": "user", "content": user_message})

    logger.info(f"知识问答(流式): {user_message[:50]}...")

    async for chunk in llm_chat_stream(
        messages=messages,
        system_prompt=QA_SYSTEM_PROMPT,
        temperature=0.7,
        max_tokens=2048,
    ):
        yield chunk