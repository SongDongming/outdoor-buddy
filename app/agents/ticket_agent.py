"""
票务查询 Agent
LangGraph 图: LLM 生成车次 → 格式化结果 → 生成接驳建议
数据源: 大模型 (DeepSeek 具备中国铁路车次知识)
"""
import json
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.base import AgentBase, create_llm
from app.utils.logger import logger


class TicketState(TypedDict, total=False):
    from_city: str
    to_city: str
    date: str
    tickets: list
    transfer_advice: str
    travel_time_advice: str
    step: str
    error: Optional[str]


TICKET_SYSTEM_PROMPT = """你是中国铁路 12306 票务数据库专家。用户查询两个城市之间的火车票，你需要返回真实存在的车次信息。

返回严格 JSON 格式（不要其他文字）：
{
  "tickets": [
    {
      "train_no": "车次编号，如 G89、D939、K117",
      "departure_time": "出发时间，如 08:00",
      "arrival_time": "到达时间，如 12:30",
      "duration": "历时，如 4小时30分",
      "seat_types": "座位类型与价格，如 二等座 ¥553 / 一等座 ¥884 / 商务座 ¥1747",
      "status": "余票状态：有票/紧张/售罄"
    }
  ]
}

规则：
1. 返回 3-6 个真实车次，包含 G(高铁)、D(动车)、K/T/Z(普速) 不同类型
2. 车次编号、时间、价格必须真实可信
3. 高铁 G 字头速度约 300km/h，动车 D 字头约 200km/h，普速约 100km/h
4. 票价参考：高铁二等座约 0.46元/km，动车约 0.31元/km，普速硬座约 0.15元/km
5. 出发时间多样化，覆盖早中晚
6. 状态大部分为"有票"，少数热门时段为"紧张"或"售罄"
7. 如果两个城市之间没有直达列车，可以返回中转方案或空数组"""


class TicketAgent(AgentBase):
    """票务查询 Agent — LLM 生成"""

    def __init__(self):
        super().__init__(name="TicketAgent", temperature=0.3)
        self.ticket_llm = create_llm(temperature=0.2, max_tokens=3072)
        self.advice_llm = create_llm(temperature=0.4, max_tokens=2048)

    def build_graph(self):
        workflow = StateGraph(TicketState)
        workflow.add_node("fetch_tickets", self._fetch_node)
        workflow.add_node("generate_advice", self._advice_node)
        workflow.set_entry_point("fetch_tickets")
        workflow.add_edge("fetch_tickets", "generate_advice")
        workflow.add_edge("generate_advice", END)
        self.graph = workflow

    async def _fetch_node(self, state: TicketState) -> dict:
        from_city = state.get("from_city", "")
        to_city = state.get("to_city", "")
        date = state.get("date", "")

        logger.info(f"[Ticket] LLM 查询: {from_city} -> {to_city}, {date}")

        tickets = []
        try:
            prompt = f"请查询 {date} 从 {from_city} 到 {to_city} 的火车票信息"
            response = await self.ticket_llm.ainvoke([
                SystemMessage(content=TICKET_SYSTEM_PROMPT),
                HumanMessage(content=prompt)
            ])
            data = self._parse_json(response.content)
            tickets = data.get("tickets", [])
            logger.info(f"[Ticket] 获取到 {len(tickets)} 个车次")
        except Exception as e:
            logger.error(f"[Ticket] LLM 生成失败: {e}")
            tickets = []

        return {"tickets": tickets, "step": "fetched"}

    async def _advice_node(self, state: TicketState) -> dict:
        tickets = state.get("tickets", [])
        from_city = state.get("from_city", "")
        to_city = state.get("to_city", "")

        if not tickets:
            return {"transfer_advice": f"未找到 {from_city} 到 {to_city} 的直达列车，建议查询中转方案或尝试其他日期。", "travel_time_advice": "", "step": "advised"}

        prompt = f"出发：{from_city} → 目的：{to_city}\n车次：{json.dumps(tickets, ensure_ascii=False)[:1200]}\n\n生成：\n1. 到站接驳建议（如何从火车站前往当地徒步/旅游出发点）\n2. 推荐出行时段（基于到达时间，哪个车次最适合户外徒步出行）"

        try:
            response = await self.advice_llm.ainvoke([HumanMessage(content=prompt)])
            text = response.content
        except Exception as e:
            logger.error(f"[Ticket] 建议生成失败: {e}")
            text = "建议到达后使用当地公共交通前往目的地。推荐选择上午出发的车次。"

        if "出行时段" in text or "推荐" in text:
            parts = text.split("出行时段", 1) if "出行时段" in text else text.split("推荐", 1)
            transfer = parts[0].strip()
            travel = (parts[1].strip() if len(parts) > 1 else "") if "出行时段" in text else ("推荐" + parts[1].strip() if len(parts) > 1 else "")
            return {"transfer_advice": transfer, "travel_time_advice": travel, "step": "advised"}

        return {"transfer_advice": text, "travel_time_advice": "建议选择上午出发的车次，预留充足时间。", "step": "advised"}

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        if "```json" in text:
            s = text.index("```json") + 7
            e = text.index("```", s)
            return json.loads(text[s:e].strip())
        if "```" in text:
            s = text.index("```") + 3
            e = text.index("```", s)
            return json.loads(text[s:e].strip())
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0:
            return json.loads(text[brace_start:brace_end])
        return {}

    async def run(self, from_city: str, to_city: str, date: str) -> dict:
        compiled = self.compile()
        result = await compiled.ainvoke({
            "from_city": from_city, "to_city": to_city, "date": date
        })
        return {
            "from_city": from_city, "to_city": to_city, "date": date,
            "tickets": result.get("tickets", []),
            "transfer_advice": result.get("transfer_advice", ""),
            "travel_time_advice": result.get("travel_time_advice", ""),
        }


_ticket_agent: Optional[TicketAgent] = None


def get_ticket_agent() -> TicketAgent:
    global _ticket_agent
    if _ticket_agent is None:
        _ticket_agent = TicketAgent()
    return _ticket_agent