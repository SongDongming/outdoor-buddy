"""
行程预案 Agent —— 生成一份完整的行程预案，分 6 个维度并行产出。

六维：海拔应对、体能分配、天气风险、环境安全、逐日指南、交通建议。

⚠️ 本 Agent 是「并发编程」的最佳范例，与其它 Agent 的最大区别：
它没有走 LangGraph 的图，而是直接用 asyncio 并发 6 个 LLM 调用——
因为 6 个维度彼此独立，串行要 6×10s≈60s，并行只需最慢那一个（约 10-15s）。
"""
from typing import Optional
import asyncio
import json
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.base import AgentBase, create_llm
from app.utils.logger import logger


class PlanAgent(AgentBase):
    """行程预案 Agent — 并行 LLM 调用生成预案各模块"""

    def __init__(self):
        super().__init__(name="PlanAgent", temperature=0.5)
        # 6 个维度共用的生成 LLM：较低温度让预案内容更稳定、专业
        self.plan_llm = create_llm(temperature=0.4, max_tokens=2048)

    async def run(self, route_params: dict, weather_data: dict = None, user_params: dict = None, ticket_data: dict = None) -> dict:
        """
        非流式：6 个 LLM 调用一次性并发，等全部完成后一起返回。
        asyncio.gather 会把 6 个协程同时跑起来，总耗时 ≈ 最慢的那个。
        """
        async def safe_call(name, coro):
            """包装单个维度调用：捕获异常，失败时返回占位文案而不是让整个预案崩掉"""
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

    async def stream_run(self, route_params: dict, weather_data: dict = None, user_params: dict = None, ticket_data: dict = None):
        """
        流式预案生成器（SSE）—— 相比 run() 更讲究体验。
        6 段预案并发执行，哪段先完成就先 yield 哪段（顺序随机，前端按 name 字段填充对应区域），
        而不是等全部完成后一次性返回。用 asyncio.wait(FIRST_COMPLETED) 实现「谁先好先给谁」。
        """
        coros = {
            "altitude_plan": self._call_altitude(route_params),
            "fitness_plan": self._call_fitness(route_params),
            "weather_risk_plan": self._call_weather(weather_data),
            "environment_knowledge": self._call_environment(route_params),
            "daily_guide": self._call_daily_guide(route_params),
            "transportation_plan": self._call_transportation(route_params, ticket_data),
        }

        async def run_one(name, coro):
            """包装单个维度：返回 (名字, 内容)，异常也返回占位文案"""
            try:
                result = await coro
                content = result.content if hasattr(result, "content") else str(result)
                return (name, content)
            except Exception as e:
                logger.error(f"PlanAgent [{name}] 失败: {e}")
                return (name, f"[{name} 生成失败，请重试]")

        # 把 6 个维度包装成 6 个 task，循环等待「先完成的那个」，逐个 yield 出去
        pending = {asyncio.create_task(run_one(n, c)): n for n, c in coros.items()}
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                name, content = task.result()
                yield {"type": "section", "name": name, "content": content}

    async def _call_altitude(self, route):
        """维度 1：海拔健康应对。先用简单规则把海拔分风险等级，再让 LLM 展开方案。"""
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
        """维度 3：天气风险应对。无天气数据时返回一个「假对象」——
        动态构造带 .content 属性的对象，让上层 `result.content` 的取值逻辑保持一致。"""
        if not weather_data:
            return type('obj', (object,), {'content': '暂无天气数据，建议出行前查询实时天气。'})()
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
        days = route.get("days", 1)
        prompt = f"{days}天行程，路线：{json.dumps(route, ensure_ascii=False)[:500]}。生成每日行动指南。"
        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是户外领队。按天输出准备事项、时间规划、注意事项。"),
            HumanMessage(content=prompt)
        ])
        return response

    async def _call_transportation(self, route, ticket_data):
        """维度 6：交通出行建议。同样在无票务数据时返回带 .content 的占位对象。"""
        if not ticket_data or not ticket_data.get('tickets'):
            return type('obj', (object,), {'content': '暂无交通票务数据，建议出行前填写出发和目的城市以获取车次建议。'})()
        tickets = ticket_data.get('tickets', [])[:5]
        route_name = route.get('route_name', '')
        location = route.get('location', '')
        prompt = f"徒步路线：{route_name}，地点：{location}。可用车次：{json.dumps(tickets, ensure_ascii=False)[:1200]}。生成交通出行建议，包括推荐车次、换乘方案、衔接时间安排。"
        response = await self.plan_llm.ainvoke([
            SystemMessage(content="你是交通出行规划专家。根据提供的车次数据输出最佳出行方案和换乘建议。"),
            HumanMessage(content=prompt)
        ])
        return response


# 全局单例：进程内只创建一次 PlanAgent
_plan_agent: Optional[PlanAgent] = None


def get_plan_agent() -> PlanAgent:
    """获取 PlanAgent 单例"""
    global _plan_agent
    if _plan_agent is None:
        _plan_agent = PlanAgent()
    return _plan_agent
