"""
知识问答 Agent —— 户外领域的通用问答，支持多轮对话（带上下文记忆）。

图结构（两节点线性，第二个节点做安全把关）：
    answer ──> safety_check ──> END

设计要点：
- answer       节点：把「历史消息 + 当前问题」一起喂给 LLM，实现多轮对话
- safety_check 节点：若回答里出现高危词（高反/失温/雷击等），再调一个 LLM 追加安全提示
- 流式模式（stream_run）为了追求逐字速度，跳过了 safety_check 的二次调用（前端另有兜底）
"""
from typing import TypedDict, Annotated, Optional
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from app.agents.base import AgentBase, create_llm


# 系统提示词（system prompt）：给 LLM 设定「人设」和约束，每次对话都会自动插到消息最前面
QA_SYSTEM = """你是户外徒步领域资深专家，覆盖五大领域：
1. 野外生存技能 2. 户外急救常识 3. 天气风险判断 4. LNT环保法则 5. 装备使用保养

要求：内容准确实用，高危场景（高反、失温、雷击、野外遇险等）必须附安全风险提示。"""


class QAState(TypedDict, total=False):
    """问答 Agent 状态。messages 用 add_messages 累加，是承载多轮对话历史的字段。"""
    messages: Annotated[list[BaseMessage], add_messages]
    answer: str
    safety_warning: str     # 命中高危场景时追加的安全提示
    step: str
    error: Optional[str]


class QAAgent(AgentBase):
    """知识问答 Agent"""

    def __init__(self):
        # temperature=0.7：问答偏开放/创意，用较高温度
        # system_prompt=QA_SYSTEM：问答 Agent 有「人设」，会随消息自动注入
        super().__init__(name="QAAgent", system_prompt=QA_SYSTEM, temperature=0.7)
        # 安全提示用极低温度(0.1) + 短 max_tokens：只要一句确定、简短的话，不要自由发挥
        self.safety_llm = create_llm(temperature=0.1, max_tokens=512)

    def build_graph(self):
        """构建两节点线性图：先回答，再做安全把关。"""
        workflow = StateGraph(QAState)

        workflow.add_node("answer", self._answer_node)
        workflow.add_node("safety_check", self._safety_check_node)

        workflow.set_entry_point("answer")
        workflow.add_edge("answer", "safety_check")
        workflow.add_edge("safety_check", END)

        self.graph = workflow

    async def _answer_node(self, state: QAState) -> dict:
        """回答节点：把（系统提示词 + 历史消息 + 当前问题）整体喂给 LLM 生成回答。"""
        messages = state.get("messages", [])
        messages = self._add_system_message(messages)

        response = await self.llm.ainvoke(messages)
        return {"answer": response.content, "step": "answered"}

    async def _safety_check_node(self, state: QAState) -> dict:
        """
        安全把关节点：本地关键词匹配（免费、即时）判断回答是否涉及高危场景。
        命中才触发第二次 LLM 调用生成安全提示；不命中则直接返回空提示，零额外成本。
        """
        answer = state.get("answer", "")
        danger_keywords = ["高反", "失温", "雷击", "危险", "遇险", "中毒", "跌落", "迷路", "冻伤", "中暑", "蛇咬", "溺水", "雪崩"]

        has_danger = any(kw in answer for kw in danger_keywords)

        if has_danger:
            safety = await self.safety_llm.ainvoke([
                SystemMessage(content="生成一句户外安全提示（15字以内）"),
                HumanMessage(content=answer[:500])
            ])
            return {"safety_warning": safety.content, "step": "safety_checked"}
        return {"safety_warning": "", "step": "safety_checked"}

    def _build_messages(self, user_message: str, context: list[dict] = None) -> list:
        """
        构建消息列表（含历史上下文）—— 实现「多轮对话」的关键。
        LLM 是无状态的，每次请求都要把之前的对话历史一起带上，它才知道上下文。
        这里把历史 context（[{role, content}, ...]）转成 LangChain 的消息对象，
        再在最后追加当前问题。
        """
        messages = []
        if context:
            for msg in context:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=user_message))
        return messages

    async def run(self, user_message: str, context: list[dict] = None) -> dict:
        """对外入口（非流式）：跑完整张图（含 safety_check），返回回答 + 安全提示。"""
        messages = self._build_messages(user_message, context)

        compiled = self.compile()
        result = await compiled.ainvoke({"messages": messages})
        return {
            "answer": result.get("answer", ""),
            "safety_warning": result.get("safety_warning", ""),
        }

    async def stream_run(self, user_message: str, context: list[dict] = None):
        """
        流式回答生成器（SSE）—— 逐 token 产出回答内容，供前端逐字显示。
        注意：流式为了逐字速度，直接用 llm.astream 绕过整张图（因此也跳过了
        safety_check 的二次调用；前端客户端另有危险关键词提示逻辑兜底）。
        """
        messages = self._add_system_message(self._build_messages(user_message, context))
        async for chunk in self.llm.astream(messages):
            content = getattr(chunk, "content", "")
            if content:
                yield content


# 全局单例：进程内只创建一次 QAAgent
_qa_agent: Optional[QAAgent] = None


def get_qa_agent() -> QAAgent:
    """获取 QAAgent 单例"""
    global _qa_agent
    if _qa_agent is None:
        _qa_agent = QAAgent()
    return _qa_agent