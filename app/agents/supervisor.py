"""
Supervisor Agent
LangGraph 图: 意图解析 → 任务分发 → 并行/串行执行 → 结果聚合
"""
import json
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.base import AgentBase, create_llm
from app.agents.route_agent import get_route_agent
from app.agents.equipment_agent import get_equipment_agent
from app.services.ticket_service import query_tickets
from app.agents.weather_agent import get_weather_agent
from app.agents.plan_agent import get_plan_agent
from app.agents.qa_agent import get_qa_agent
from app.utils.logger import logger


class SupervisorState(TypedDict, total=False):
    user_message: str
    session_context: dict
    tasks: list
    results: dict
    response: str
    step: str
    error: Optional[str]


class SupervisorAgent(AgentBase):
    """全局协调 Agent"""

    def __init__(self):
        super().__init__(name="SupervisorAgent", temperature=0.3)
        self.router_llm = create_llm(temperature=0.1, max_tokens=1024)

    def build_graph(self):
        workflow = StateGraph(SupervisorState)

        workflow.add_node("parse_intent", self._parse_node)
        workflow.add_node("execute_tasks", self._execute_node)
        workflow.add_node("aggregate", self._aggregate_node)

        workflow.set_entry_point("parse_intent")
        workflow.add_edge("parse_intent", "execute_tasks")
        workflow.add_edge("execute_tasks", "aggregate")
        workflow.add_edge("aggregate", END)

        self.graph = workflow

    async def _parse_node(self, state: SupervisorState) -> dict:
        user_message = state.get("user_message", "")
        context = state.get("session_context", {})

        prompt = f"""你是户外助手意图解析器。用户输入：「{user_message}」

可用模块：route(路线), weather(天气), ticket(票务), equipment(装备), plan(预案), qa(问答)

返回 JSON：{{"tasks":[{{"module":"模块名","params":{{}}}}],"response":"直接回复或追问"}}

规则：
- 指代词（那里/这个地方）从上下文提取地点
- 信息不全时标记追问
- 多模块请求拆分为多个 tasks"""

        response = await self.router_llm.ainvoke([HumanMessage(content=prompt)])
        try:
            data = self._parse_json(response.content)
            return {"tasks": data.get("tasks", []), "response": data.get("response", ""), "step": "parsed"}
        except Exception:
            return {"tasks": [{"module": "qa", "params": {"question": user_message}}], "response": "", "step": "parsed"}

    async def _execute_node(self, state: SupervisorState) -> dict:
        tasks = state.get("tasks", [])
        results = {}

        for task in tasks:
            module = task.get("module", "")
            params = task.get("params", {})

            try:
                if module == "route":
                    results["route"] = await get_route_agent().run(params.get("keyword", params.get("location", "")))
                elif module == "weather":
                    results["weather"] = await get_weather_agent().run(params.get("location", ""))
                elif module == "ticket":
                    results["ticket"] = await query_tickets(params.get("from", ""), params.get("to", ""), params.get("date", ""))
                elif module == "equipment":
                    results["equipment"] = await get_equipment_agent().run(params)
                elif module == "plan":
                    results["plan"] = await get_plan_agent().run(params.get("route_params", {}), params.get("weather_data"), params.get("user_params"))
                elif module == "qa":
                    results["qa"] = await get_qa_agent().run(params.get("question", ""))
            except Exception as e:
                logger.error(f"[Supervisor] 任务执行失败 [{module}]: {e}")
                results[module] = {"error": str(e)}

        return {"results": results, "step": "executed"}

    async def _aggregate_node(self, state: SupervisorState) -> dict:
        results = state.get("results", {})
        response = state.get("response", "")

        if not response and results:
            parts = []
            for module, data in results.items():
                if module == "route" and data.get("routes"):
                    parts.append(f"找到 {len(data['routes'])} 条路线")
                elif module == "weather" and data.get("forecast"):
                    parts.append("天气数据已获取")
                elif module == "ticket" and data.get("tickets"):
                    parts.append(f"找到 {len(data['tickets'])} 个车次")
                elif module == "qa" and data.get("answer"):
                    parts.append(data["answer"][:100])
            response = "；".join(parts) if parts else "查询完成"

        return {"response": response, "step": "aggregated"}

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        if "```json" in text:
            return json.loads(text[text.index("```json") + 7:text.index("```", text.index("```json") + 7)].strip())
        if "```" in text:
            return json.loads(text[text.index("```") + 3:text.index("```", text.index("```") + 3)].strip())
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0:
            return json.loads(text[brace_start:brace_end])
        raise ValueError("无法解析 JSON")

    async def run(self, user_message: str, session_context: dict = None) -> dict:
        compiled = self.compile()
        result = await compiled.ainvoke({
            "user_message": user_message,
            "session_context": session_context or {},
        })
        return {
            "tasks": result.get("tasks", []),
            "results": result.get("results", {}),
            "response": result.get("response", ""),
        }


_supervisor_agent: Optional[SupervisorAgent] = None


def get_supervisor_agent() -> SupervisorAgent:
    global _supervisor_agent
    if _supervisor_agent is None:
        _supervisor_agent = SupervisorAgent()
    return _supervisor_agent