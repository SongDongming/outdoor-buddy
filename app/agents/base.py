"""
Agent 基类模块 —— 所有智能体共用的「地基」。

本模块提供三块被每个 Agent 复用的基础设施：
1. create_llm()    —— 统一的大模型客户端工厂（ChatOpenAI 指向 DeepSeek 等 OpenAI 兼容服务）
2. BaseAgentState  —— Agent 各节点之间传递数据的「状态」类型定义
3. AgentBase       —— 所有 Agent 的父类，封装「构建图 → 编译图 → 运行图」的标准流程

LangGraph 三个核心概念（后面每个 Agent 都会反复出现）：
- StateGraph：把一次任务抽象成一张「有向图」，由节点(node)和边(edge)组成
- 节点(node)：一个处理步骤（通常是调用一次 LLM 或做一次逻辑判断），输入输出都是 state
- 边(edge)  ：节点间的流转；add_edge 是固定顺序，add_conditional_edges 是按条件分叉
"""
from typing import TypedDict, Annotated, Optional
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage
from app.core.config import get_settings
from app.utils.logger import logger

settings = get_settings()


def _get_proxy_url() -> str | None:
    """获取代理 URL，自动处理 Docker 容器内 localhost → host.docker.internal 转换"""
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
    """
    创建 LangChain 的 ChatOpenAI 实例（大模型客户端工厂）。

    关键设计：这里用的是 ChatOpenAI 而非某个具体厂商的 SDK——
    只要目标服务提供 OpenAI 兼容接口（DeepSeek、通义、月之暗面等都兼容），
    改一下 COMPATIBLE_BASE_URL / COMPATIBLE_MODEL 环境变量就能换模型，代码零改动。

    参数说明：
    - temperature：随机性。0=最确定（适合生成 JSON/结构化数据），1=最有创意（适合聊天）
    - max_tokens ：单次回复的最大 token 数（约等于「最长能说多少字」）
    - model      ：覆盖全局默认模型（多数 Agent 用默认，结构化输出场景可指定更稳的模型）
    """
    return ChatOpenAI(
        # 服务地址与密钥，均来自环境变量（见 app/core/config.py）
        api_key=settings.compatible_api_key,
        base_url=settings.compatible_base_url,
        model=model or settings.compatible_model,
        temperature=temperature,
        max_tokens=max_tokens,
        # 显式传入 http 客户端，便于挂代理（国内访问 OpenAI 兼容服务常需代理）
        http_client=_build_http_client(),
        http_async_client=_build_async_http_client(),
    )


class BaseAgentState(TypedDict, total=False):
    """
    Agent 基础状态 —— 图里各节点之间靠它传递数据。

    - TypedDict   ：用「类型注解」定义一个字典结构，方便类型检查
    - total=False ：所有字段都是可选的（节点可以只返回它更新的字段，其余字段自动合并）
    - Annotated[..., add_messages]：特殊之处 —— 当多个节点都往 messages 里追加内容时，
      不是「覆盖」而是「累加」，这是 LangGraph 用来实现多轮对话消息历史的机制。
    """
    messages: Annotated[list[BaseMessage], add_messages]
    input: str
    output: str
    error: Optional[str]
    metadata: dict


class AgentBase:
    """
    LangGraph Agent 基类 —— 定义了每个智能体的「模板方法」流程。

    子类只需做两件事：
    1. 在 __init__ 里调用 super().__init__(...) 设置名字、提示词、温度
    2. 重写 build_graph() 定义自己的节点和边

    之后调用 run()/stream_run() 时，基类会自动「构建→编译→执行」。
    """

    def __init__(self, name: str, system_prompt: str = "", temperature: float = 0.7):
        self.name = name
        self.llm = create_llm(temperature=temperature)  # 每个 Agent 一个主 LLM
        self.system_prompt = system_prompt               # 可选：自动插到消息最前的系统提示词
        self.graph: Optional[StateGraph] = None          # 未编译的图定义
        self._compiled = None                            # 编译后的图（懒编译，只编译一次）

    def build_graph(self) -> None:
        """子类重写此方法构建图结构（本类只定义契约，不实现）"""
        raise NotImplementedError

    def compile(self):
        """
        编译图（懒编译 + 缓存）。
        图编译是一次性开销，所以第一次调用才真正 build，之后复用 _compiled；
        这也是每个 Agent 都被做成「全局单例」能省下的成本。
        """
        if self._compiled is None:
            self.build_graph()
            self._compiled = self.graph.compile()
        return self._compiled

    async def run(self, state: dict) -> dict:
        """
        执行 Agent（非流式）：一次性跑完整张图，返回最终 state。
        ainvoke 是 LangGraph 的异步执行入口；出错时兜底返回 error 字段，而不是让异常向上冒泡。
        """
        compiled = self.compile()
        try:
            result = await compiled.ainvoke(state)
            logger.info(f"[{self.name}] 执行成功")
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 执行失败: {e}")
            return {"output": "", "error": str(e), "messages": state.get("messages", [])}

    def _add_system_message(self, messages: list) -> list:
        """
        在消息列表开头插入系统提示词（system prompt 用来给 LLM 设定「人设」和规则）。
        若最前面已经是系统消息（或没配 system_prompt），则原样返回，避免重复插入。
        """
        if self.system_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
            return [SystemMessage(content=self.system_prompt)] + list(messages)
        return messages