"""
路线搜索 Agent —— 输入徒步地点关键词，让 LLM 生成结构化的路线数据。

图结构（一张三节点的有向图，带一个条件分叉）：
    search ──> validate ──(有条件)──> enrich ──> END
                          └──────(空结果)──────> END

设计要点：
- search  节点让 LLM 以「严格 JSON」格式输出路线列表（结构化数据便于前端渲染）
- validate 节点做数据质量把关：过滤掉字段残缺的脏数据
- enrich  节点对高海拔路线补充安全提示（用第二个 LLM 调用）
"""
import json
import operator
from typing import TypedDict, Annotated, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.base import AgentBase, create_llm
from app.utils.logger import logger


class RouteState(TypedDict, total=False):
    """路线 Agent 的状态。各节点通过它读写数据，只在需要时更新对应字段。"""
    keyword: str
    # Annotated[list, operator.add]：多个节点往 routes 里加数据时是「累加」而不是覆盖
    routes: Annotated[list, operator.add]
    summary: str
    step: str          # 记录当前进度，供条件分支判断下一步往哪走
    error: Optional[str]


class RouteAgent(AgentBase):
    """徒步路线搜索 Agent"""

    def __init__(self):
        super().__init__(
            name="RouteAgent",
            temperature=0.3,
        )
        # 用更低温度(0.2)的专用 LLM 做结构化输出：
        # 温度越低随机性越小，输出越「老实」，更容易稳定地吐 JSON，而不是自由发挥
        self.structured_llm = create_llm(temperature=0.2, max_tokens=4096)

    def build_graph(self):
        """
        构建图结构（只描述「有哪些节点、怎么连接」，不真正执行）。
        set_entry_point 指定入口；add_edge 固定流转；add_conditional_edges 条件分叉。
        """
        workflow = StateGraph(RouteState)

        # 三个节点，每个节点 = 一个处理函数
        workflow.add_node("search", self._search_node)
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("enrich", self._enrich_node)

        workflow.set_entry_point("search")
        workflow.add_edge("search", "validate")

        # 条件边：validate 之后根据 _route_decision 的返回值决定走 enrich 还是直接 END
        workflow.add_conditional_edges(
            "validate",
            self._route_decision,
            {"enrich": "enrich", "end": END}
        )
        workflow.add_edge("enrich", END)

        self.graph = workflow

    async def _search_node(self, state: RouteState) -> dict:
        """
        搜索节点：把关键词交给 LLM，要求它返回严格 JSON。
        提示词里「返回严格 JSON（不要其他文字）」是关键——这样后端才能 json.loads 解析，
        这也是为什么单独用了 temperature=0.2 的 structured_llm。
        """
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
        """
        验证节点：数据质量把关。LLM 可能偶尔返回字段残缺的路线，
        这里把它过滤掉；若过滤后为空，则 step 标记为 "empty"（触发条件分支直接结束）。
        """
        routes = state.get("routes", [])
        if not routes:
            return {"step": "empty"}
        # 过滤掉字段不完整的路线（name 和 distance 是必填的最低要求）
        valid = [r for r in routes if r.get("name") and r.get("distance")]
        return {"routes": valid, "step": "validated"}

    async def _enrich_node(self, state: RouteState) -> dict:
        """
        充实节点：对高海拔路线补充安全提示。
        这是一个「条件触发」的二次 LLM 调用——只有存在海拔 >3000 的路线时才调用，
        避免不必要的 LLM 开销（每次调用都是钱和时间）。
        """
        routes = state.get("routes", [])
        summary = state.get("summary", "")

        # 检查是否存在海拔 >3000 的路线（先把「米」字去掉再转数字）
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
        """
        条件分支的「决策函数」：根据 state 返回下一个节点的名字。
        返回的字符串必须能匹配 add_conditional_edges 里定义的映射表 key。
        """
        if state.get("step") == "empty":
            return "end"       # 空结果：直接结束，不再 enrich
        return "enrich"

    def _parse_json(self, text: str) -> dict:
        """
        容错地解析 LLM 输出的 JSON。
        LLM 经常「不听话」地在 JSON 外面套 ```json 代码块、或夹杂说明文字，
        所以这里用一串 fallback：先直接 parse，再尝试剥掉代码块围栏，最后暴力截取花括号。
        """
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
        """
        对外入口：接收关键词，跑完整张图，整理成 API 需要的字典。
        注意这里返回的字段名（routes / llm_summary）是「对外协议」，和内部 state 字段解耦。
        """
        compiled = self.compile()
        result = await compiled.ainvoke({"keyword": keyword})
        return {
            "keyword": keyword,
            "routes": result.get("routes", []),
            "llm_summary": result.get("summary", ""),
            "source": "langgraph",
        }


# 全局单例：整个进程只创建一次 RouteAgent（图只编译一次，省资源）
_route_agent: Optional[RouteAgent] = None


def get_route_agent() -> RouteAgent:
    """获取 RouteAgent 单例（首次调用时创建，之后复用）"""
    global _route_agent
    if _route_agent is None:
        _route_agent = RouteAgent()
    return _route_agent