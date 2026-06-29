"""
大模型统一调用工具类
封装 OpenAI 兼容接口，支持同步与流式两种调用方式，提供统一入口供业务层调用
"""
from typing import AsyncGenerator, Optional
from openai import AsyncOpenAI
from app.core.config import get_settings
from app.utils.logger import logger

settings = get_settings()

# 全局异步客户端单例
_client: Optional[AsyncOpenAI] = None


def _get_proxy_url() -> str | None:
    """获取代理 URL，自动处理 Docker 容器内 localhost → host.docker.internal 转换"""
    proxy = settings.https_proxy or settings.http_proxy
    if proxy:
        proxy = proxy.replace("127.0.0.1", "host.docker.internal")
        proxy = proxy.replace("localhost", "host.docker.internal")
    return proxy


def get_llm_client() -> AsyncOpenAI:
    """获取大模型客户端单例"""
    global _client
    if _client is None:
        import httpx
        kwargs = {
            "api_key": settings.compatible_api_key,
            "base_url": settings.compatible_base_url,
        }
        proxy = _get_proxy_url()
        if proxy:
            kwargs["http_client"] = httpx.AsyncClient(proxy=proxy)
            logger.info(f"大模型客户端初始化完成: {settings.compatible_model} (代理: {proxy})")
        else:
            logger.info(f"大模型客户端初始化完成: {settings.compatible_model}")
        _client = AsyncOpenAI(**kwargs)
    return _client


async def llm_chat(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
) -> str:
    """
    同步（非流式）调用大模型
    Args:
        messages: 对话消息列表 [{"role": "user", "content": "..."}]
        temperature: 温度参数
        max_tokens: 最大 token 数
        system_prompt: 系统提示词（可选，会插入 messages 开头）
    Returns:
        模型返回的文本内容
    """
    client = get_llm_client()

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    try:
        response = await client.chat.completions.create(
            model=settings.compatible_model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        logger.info(f"大模型调用成功, tokens: {response.usage}")
        return content
    except Exception as e:
        import traceback
        logger.error(f"大模型调用失败: {e}\n{traceback.format_exc()}")
        raise


async def llm_chat_stream(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    流式调用大模型
    Args:
        messages: 对话消息列表
        temperature: 温度参数
        max_tokens: 最大 token 数
        system_prompt: 系统提示词
    Yields:
        逐段返回的文本内容
    """
    client = get_llm_client()

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    try:
        stream = await client.chat.completions.create(
            model=settings.compatible_model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        logger.error(f"大模型流式调用失败: {e}")
        raise