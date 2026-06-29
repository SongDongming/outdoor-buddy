"""
知识问答 Agent
LangGraph 图: 接收问题 → 知识检索 → 生成回答 → 安全审核
"""
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from typing import Annotated
from app.agents.base import AgentBase, create_llm
from app.utils.logger import logger


QA_SYSTEM = """你是户外徒步领域资深专家，覆盖五大领域：
1. 野外生存技能 2. 户外急救常识 3. 天气风险判断 4. LNT环保法则 5. 装备使用保养

要求：内容准确实用，高危场景（高反、失温、雷击、野外遇险等）必须附安全风险提示。"""


class QAState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    answer: str
    safety_warning: str
    step: str
    error: Optional[str]


class QAAgent(AgentBase):
    """知识问答 Agent"""

    def __init__(self):
        super().__init__(name="QAAgent", system_prompt=QA_SYSTEM, temperature=0.7)
        self.safety_llm = create_llm(temperature=0.1, max_tokens=512)

    def build_graph(self):
        workflow = StateGraph(QAState)

        workflow.add_node("answer", self._answer_node)
        workflow.add_node("safety_check", self._safety_check_node)

        workflow.set_entry_point("answer")
        workflow.add_edge("answer", "safety_check")
        workflow.add_edge("safety_check", END)

        self.graph = workflow

    async def _answer_node(self, state: QAState) -> dict:
        messages = state.get("messages", [])
        messages = self._add_system_message(messages)

        response = await self.llm.ainvoke(messages)
        return {"answer": response.content, "step": "answered"}

    async def _safety_check_node(self, state: QAState) -> dict:
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

    async def run(self, user_message: str, context: list[dict] = None) -> dict:
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

        compiled = self.compile()
        result = await compiled.ainvoke({"messages": messages})
        return {
            "answer": result.get("answer", ""),
            "safety_warning": result.get("safety_warning", ""),
        }


_qa_agent: Optional[QAAgent] = None


def get_qa_agent() -> QAAgent:
    global _qa_agent
    if _qa_agent is None:
        _qa_agent = QAAgent()
    return _qa_agent