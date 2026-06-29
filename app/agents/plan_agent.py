"""
行程预案 Agent
LangGraph 图: 整合参数 → 海拔评估 → 体能规划 → 天气应对 → 环境知识 → 逐日指南
"""
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.base import AgentBase, create_llm
from app.utils.logger import logger


class PlanState(TypedDict, total=False):
    route_params: dict
    weather_data: dict | None
    user_params: dict | None
    altitude_plan: str
    fitness_plan: str
    weather_risk_plan: str
    environment_knowledge: str
    daily_guide: str
    step: str
    error: Optional[str]


class PlanAgent(AgentBase):
    """行程预案 Agent"""

    def __init__(self):
        super().__init__(name="PlanAgent", temperature=0.5)
        self.plan_llm = create_llm(temperature=0.4, max_tokens=2048)

    def build_graph(self):
        workflow = StateGraph(PlanState)

        workflow.add_node("altitude", self._altitude_node)
        workflow.add_node("fitness", self._fitness_node)
        workflow.add_node("weather_risk", self._weather_risk_node)
        workflow.add_node("environment", self._environment_node)
        workflow.add_node("daily_guide", self._daily_guide_node)

        workflow.set_entry_point("altitude")
        workflow.add_edge("altitude", "fitness")
        workflow.add_edge("fitness", "weather_risk")
        workflow.add_edge("weather_risk", "environment")
        workflow.add_edge("environment", "daily_guide")
        workflow.add_edge("daily_guide", END)

        self.graph = workflow

    async def _altitude_node(self, state: PlanState) -> dict:
        route = state.get("route_params", {})
        max_alt = route.get("max_altitude", 0)
        days = route.get("days", 1)

        level = "低风险" if max_alt < 3000 else ("中风险" if max_alt < 4000 else "高风险")
        prompt = f"最高海拔{max_alt}米（{level}），{days}天。生成海拔适应方案、高反应对、必备药品清单。"

        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是高海拔户外医学专家。输出海拔健康应对方案。"),
            HumanMessage(content=prompt)
        ])
        return {"altitude_plan": response.content, "step": "altitude_done"}

    async def _fitness_node(self, state: PlanState) -> dict:
        route = state.get("route_params", {})
        prompt = f"徒步{route.get('days',1)}天，爬升{route.get('elevation_gain',0)}米，难度{route.get('difficulty','中等')}。生成体能分配建议、休息节点、补水节奏。"

        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是户外体能训练专家。输出每日行程分配建议。"),
            HumanMessage(content=prompt)
        ])
        return {"fitness_plan": response.content, "step": "fitness_done"}

    async def _weather_risk_node(self, state: PlanState) -> dict:
        weather = state.get("weather_data")
        if not weather:
            return {"weather_risk_plan": "暂无天气数据，建议出行前查询实时天气。", "step": "weather_done"}

        import json
        prompt = f"天气数据：{json.dumps(weather, ensure_ascii=False)[:1000]}。生成天气风险应对预案。"

        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是户外天气风险专家。输出装备调整和避险要点。"),
            HumanMessage(content=prompt)
        ])
        return {"weather_risk_plan": response.content, "step": "weather_done"}

    async def _environment_node(self, state: PlanState) -> dict:
        terrain = state.get("route_params", {}).get("terrain", "山地")
        prompt = f"地形：{terrain}。推送迷路应对、野生动物防范、水源安全、LNT准则、应急求救知识。"

        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是户外安全专家。输出针对性环境安全知识。"),
            HumanMessage(content=prompt)
        ])
        return {"environment_knowledge": response.content, "step": "env_done"}

    async def _daily_guide_node(self, state: PlanState) -> dict:
        import json
        route = state.get("route_params", {})
        days = route.get("days", 1)
        prompt = f"{days}天行程，路线：{json.dumps(route, ensure_ascii=False)[:500]}。生成每日行动指南。"

        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是户外领队。按天输出准备事项、时间规划、注意事项。"),
            HumanMessage(content=prompt)
        ])
        return {"daily_guide": response.content, "step": "guide_done"}

    async def run(self, route_params: dict, weather_data: dict = None, user_params: dict = None, ticket_data: dict = None) -> dict:
        """并行执行 6 个 LLM 调用，大幅缩短总耗时"""
        import asyncio

        async def safe_call(name, coro):
            try:
                result = await coro
                return (name, result.content if hasattr(result, 'content') else str(result))
            except Exception as e:
                logger.error(f"PlanAgent [{name}] 失败: {e}")
                return (name, f"[{name} 生成失败，请重试]")

        tasks = [
            safe_call("altitude_plan", self._call_altitude(route_params)),
            safe_call("fitness_plan", self._call_fitness(route_params)),
            safe_call("weather_risk_plan", self._call_weather(weather_data)),
            safe_call("environment_knowledge", self._call_environment(route_params)),
            safe_call("daily_guide", self._call_daily_guide(route_params)),
            safe_call("transportation_plan", self._call_transportation(route_params, ticket_data)),
        ]

        results = dict(await asyncio.gather(*tasks))
        logger.info(f"PlanAgent 并行生成完成: {list(results.keys())}")
        return results

    async def _call_altitude(self, route):
        max_alt = route.get("max_altitude", 0)
        days = route.get("days", 1)
        level = "低风险" if max_alt < 3000 else ("中风险" if max_alt < 4000 else "高风险")
        prompt = f"最高海拔{max_alt}米（{level}），{days}天。生成海拔适应方案、高反应对、必备药品清单。"
        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是高海拔户外医学专家。输出海拔健康应对方案。"),
            HumanMessage(content=prompt)
        ])
        return response

    async def _call_fitness(self, route):
        prompt = f"徒步{route.get('days',1)}天，爬升{route.get('elevation_gain',0)}米，难度{route.get('difficulty','中等')}。生成体能分配建议、休息节点、补水节奏。"
        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是户外体能训练专家。输出每日行程分配建议。"),
            HumanMessage(content=prompt)
        ])
        return response

    async def _call_weather(self, weather_data):
        if not weather_data:
            return type('obj', (object,), {'content': '暂无天气数据，建议出行前查询实时天气。'})()
        import json
        prompt = f"天气数据：{json.dumps(weather_data, ensure_ascii=False)[:1000]}。生成天气风险应对预案。"
        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是户外天气风险专家。输出装备调整和避险要点。"),
            HumanMessage(content=prompt)
        ])
        return response

    async def _call_environment(self, route):
        terrain = route.get("terrain", "山地")
        prompt = f"地形：{terrain}。推送迷路应对、野生动物防范、水源安全、LNT准则、应急求救知识。"
        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是户外安全专家。输出针对性环境安全知识。"),
            HumanMessage(content=prompt)
        ])
        return response

    async def _call_daily_guide(self, route):
        import json
        days = route.get("days", 1)
        prompt = f"{days}天行程，路线：{json.dumps(route, ensure_ascii=False)[:500]}。生成每日行动指南。"
        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是户外领队。按天输出准备事项、时间规划、注意事项。"),
            HumanMessage(content=prompt)
        ])
        return response

    async def _call_transportation(self, route, ticket_data):
        if not ticket_data or not ticket_data.get('tickets'):
            return type('obj', (object,), {'content': '暂无交通票务数据，建议出行前填写出发和目的城市以获取车次建议。'})()
        import json
        tickets = ticket_data.get('tickets', [])[:5]
        route_name = route.get('route_name', '')
        location = route.get('location', '')
        prompt = f"徒步路线：{route_name}，地点：{location}。可用车次：{json.dumps(tickets, ensure_ascii=False)[:1200]}。生成交通出行建议，包括推荐车次、换乘方案、衔接时间安排。"
        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是交通出行规划专家。根据提供的车次数据输出最佳出行方案和换乘建议。"),
            HumanMessage(content=prompt)
        ])
        return response


_plan_agent: Optional[PlanAgent] = None


def get_plan_agent() -> PlanAgent:
    global _plan_agent
    if _plan_agent is None:
        _plan_agent = PlanAgent()
    return _plan_agent