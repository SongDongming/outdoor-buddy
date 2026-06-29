"""
路线搜索 Agent
LangGraph 图: 解析关键词 → 搜索路线知识 → 结构化输出 → 安全审核
"""
import json
import operator
from typing import TypedDict, Annotated, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.base import AgentBase, create_llm
from app.utils.logger import logger


class RouteState(TypedDict, total=False):
    keyword: str
    routes: Annotated[list, operator.add]
    summary: str
    step: str
    error: Optional[str]


class RouteAgent(AgentBase):
    """徒步路线搜索 Agent"""

    def __init__(self):
        super().__init__(
            name="RouteAgent",
            temperature=0.3,
        )
        self.structured_llm = create_llm(temperature=0.2, max_tokens=4096)

    def build_graph(self):
        workflow = StateGraph(RouteState)

        workflow.add_node("search", self._search_node)
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("enrich", self._enrich_node)

        workflow.set_entry_point("search")
        workflow.add_edge("search", "validate")
        workflow.add_conditional_edges(
            "validate",
            self._route_decision,
            {"enrich": "enrich", "end": END}
        )
        workflow.add_edge("enrich", END)

        self.graph = workflow

    async def _search_node(self, state: RouteState) -> dict:
        """搜索路线知识节点"""
        keyword = state.get("keyword", "")
        logger.info(f"[RouteAgent] 搜索: {keyword}")

        prompt = f"""你是中国户外徒步路线数据库。请提供关于「{keyword}」的知名徒步路线。

返回严格 JSON（不要其他文字）：
{{
  "routes": [
    {{
      "name": "路线完整名称",
      "distance": "全程距离",
      "elevation_gain": "累计爬升",
      "max_altitude": "最高海拔",
      "difficulty": "简单/中等/困难/专业",
      "duration": "预计耗时",
      "best_season": "最佳季节",
      "summary": "路线特点简介",
      "rating": "评分如4.5/5"
    }}
  ],
  "summary": "整体分析、优缺点、适合人群、安全提示"
}}

返回 2-5 条真实存在的路线。海拔>3000米必须附安全提示。"""

        response = await self.structured_llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=f"请提供关于「{keyword}」的徒步路线信息")
        ])

        try:
            data = self._parse_json(response.content)
            return {
                "routes": data.get("routes", []),
                "summary": data.get("summary", ""),
                "step": "searched",
            }
        except Exception as e:
            import traceback
            logger.error(f"[RouteAgent] JSON解析失败: {e}\n{traceback.format_exc()}")
            return {"routes": [], "summary": "", "step": "searched", "error": str(e)}

    async def _validate_node(self, state: RouteState) -> dict:
        """验证节点：确保路线数据质量"""
        routes = state.get("routes", [])
        if not routes:
            return {"step": "empty"}
        # 过滤掉字段不完整的路线
        valid = [r for r in routes if r.get("name") and r.get("distance")]
        return {"routes": valid, "step": "validated"}

    async def _enrich_node(self, state: RouteState) -> dict:
        """充实节点：补充安全提示"""
        routes = state.get("routes", [])
        summary = state.get("summary", "")

        # 检查是否需要高海拔安全提示
        has_high_altitude = any(
            r.get("max_altitude", "").replace("米", "").isdigit()
            and int(r["max_altitude"].replace("米", "")) > 3000
            for r in routes
        )

        if has_high_altitude and "海拔" not in summary:
            safety_note = await self.llm.ainvoke([
                SystemMessage(content="为高海拔路线生成30字安全提示"),
                HumanMessage(content=f"路线: {json.dumps(routes, ensure_ascii=False)[:500]}")
            ])
            summary = summary + "\n\n⚠️ 高海拔安全提示：" + safety_note.content

        return {"summary": summary, "step": "enriched"}

    def _route_decision(self, state: RouteState) -> str:
        if state.get("step") == "empty":
            return "end"
        return "enrich"

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        if "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            return json.loads(text[brace_start:brace_end])
        raise ValueError("无法解析 JSON")

    async def run(self, keyword: str) -> dict:
        compiled = self.compile()
        result = await compiled.ainvoke({"keyword": keyword})
        return {
            "keyword": keyword,
            "routes": result.get("routes", []),
            "llm_summary": result.get("summary", ""),
            "source": "langgraph",
        }


# 全局单例
_route_agent: Optional[RouteAgent] = None


def get_route_agent() -> RouteAgent:
    global _route_agent
    if _route_agent is None:
        _route_agent = RouteAgent()
    return _route_agent