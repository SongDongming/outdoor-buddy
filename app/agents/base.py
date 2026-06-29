"""
Agent 基类模块
提供 LangGraph 通用的 LLM 工厂、State 定义和图构建工具
"""
from typing import TypedDict, Annotated, Optional
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from app.core.config import get_settings
from app.utils.logger import logger

settings = get_settings()


def _get_proxy_url() -> str | None:
    """获取代理 URL，自动处理 Docker 容器内 localhost → host.docker.internal 转换"""
    import os
    proxy = settings.https_proxy or settings.http_proxy
    if proxy:
        # Docker 容器内 127.0.0.1 指向容器自身，需替换为 host.docker.internal
        proxy = proxy.replace("127.0.0.1", "host.docker.internal")
        proxy = proxy.replace("localhost", "host.docker.internal")
    return proxy


def _build_http_client(timeout: float = 60):
    """构建带代理的 httpx 同步客户端（供 ChatOpenAI http_client 使用）"""
    import httpx
    proxy = _get_proxy_url()
    if proxy:
        return httpx.Client(proxy=proxy, timeout=timeout)
    return httpx.Client(timeout=timeout)


def _build_async_http_client(timeout: float = 120):
    """构建带代理的 httpx 异步客户端（供 ChatOpenAI http_async_client 使用）"""
    import httpx
    proxy = _get_proxy_url()
    if proxy:
        return httpx.AsyncClient(proxy=proxy, timeout=timeout)
    return httpx.AsyncClient(timeout=timeout)


def create_llm(
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: Optional[str] = None,
) -> ChatOpenAI:
    """创建 LangChain ChatOpenAI 实例"""
    return ChatOpenAI(
        api_key=settings.compatible_api_key,
        base_url=settings.compatible_base_url,
        model=model or settings.compatible_model,
        temperature=temperature,
        max_tokens=max_tokens,
        http_client=_build_http_client(),
        http_async_client=_build_async_http_client(),
    )


class BaseAgentState(TypedDict, total=False):
    """Agent 基础状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    input: str
    output: str
    error: Optional[str]
    metadata: dict


class AgentBase:
    """LangGraph Agent 基类"""

    def __init__(self, name: str, system_prompt: str = "", temperature: float = 0.7):
        self.name = name
        self.llm = create_llm(temperature=temperature)
        self.system_prompt = system_prompt
        self.graph: Optional[StateGraph] = None
        self._compiled = None

    def build_graph(self) -> None:
        """子类重写此方法构建图结构"""
        raise NotImplementedError

    def compile(self):
        """编译图"""
        if self._compiled is None:
            self.build_graph()
            self._compiled = self.graph.compile()
        return self._compiled

    async def run(self, state: dict) -> dict:
        """执行 Agent"""
        compiled = self.compile()
        try:
            result = await compiled.ainvoke(state)
            logger.info(f"[{self.name}] 执行成功")
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 执行失败: {e}")
            return {"output": "", "error": str(e), "messages": state.get("messages", [])}

    def _add_system_message(self, messages: list) -> list:
        """在消息列表开头添加系统提示词"""
        if self.system_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
            return [SystemMessage(content=self.system_prompt)] + list(messages)
        return messages