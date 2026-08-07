"""
装备推荐 Agent
LangGraph 图: 参数提取 → 模式匹配 → 装备生成 → 价格评估
"""
import operator
from typing import TypedDict, Annotated, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.base import AgentBase, create_llm
from app.utils.logger import logger


class EquipmentState(TypedDict, total=False):
    mode: str
    days: int
    season: str
    terrain: str
    people_count: int
    equipment_list: str
    buying_advice: str
    price_range: str
    lightweight_alternatives: str
    step: str
    error: Optional[str]


class EquipmentAgent(AgentBase):
    """装备推荐 Agent"""

    def __init__(self):
        super().__init__(name="EquipmentAgent", temperature=0.5)
        self.structured_llm = create_llm(temperature=0.3, max_tokens=4096)

    def build_graph(self):
        workflow = StateGraph(EquipmentState)

        workflow.add_node("analyze_params", self._analyze_params)
        workflow.add_node("generate_equipment", self._generate_equipment)
        workflow.add_node("estimate_price", self._estimate_price)

        workflow.set_entry_point("analyze_params")
        workflow.add_edge("analyze_params", "generate_equipment")
        workflow.add_edge("generate_equipment", "estimate_price")
        workflow.add_edge("estimate_price", END)

        self.graph = workflow

    async def _analyze_params(self, state: EquipmentState) -> dict:
        mode = state.get("mode", "light")
        mode_label = "重装徒步（全程背负，需帐篷睡袋炊具等全套露营装备）" if mode == "heavy" else "轻装徒步（沿途有补给住宿，仅需当日装备）"
        return {"mode": mode, "mode_label": mode_label, "step": "analyzed"}

    @staticmethod
    def _equipment_prompt(mode_label: str, days: int, season: str, terrain: str) -> str:
        """生成装备清单的提示词"""
        return f"""你是户外装备专家。根据参数生成装备清单。

参数：{mode_label}，{days}天，{season}季，{terrain}地形

按以下分类输出（每件装备含名称、品牌建议、选购要点、参考价格）：
1. 服装类（冲锋衣、速干衣、保暖层）
2. 鞋靴类
3. 背包类
4. {'帐篷/睡眠类（睡袋、防潮垫）' if '重装' in mode_label else '饮水/路餐类'}
5. {'炊具/饮食类（炉头、锅具）' if '重装' in mode_label else ''}
6. 登山配件（登山杖、头灯、护膝、帽子）
7. 急救用品

最后给出轻量化替代方案建议。"""

    @staticmethod
    def _price_prompt(equipment_list: str, mode: str) -> str:
        """生成价格评估的提示词"""
        return f"""根据以下装备清单，评估总预算区间和选购建议。
{mode}模式，装备清单：
{equipment_list[:2000]}

输出格式：
【选购建议】一句话
【价格区间】轻装日徒步 1000-3000 元，重装多日 3000-8000 元的具体建议
【轻量化替代】核心轻量化推荐"""

    async def _generate_equipment(self, state: EquipmentState) -> dict:
        mode_label = state.get("mode_label", "")
        days = state.get("days", 1)
        season = state.get("season", "夏")
        terrain = state.get("terrain", "山地")

        prompt = self._equipment_prompt(mode_label, days, season, terrain)
        response = await self.structured_llm.ainvoke([HumanMessage(content=prompt)])
        return {"equipment_list": response.content, "step": "generated"}

    async def _estimate_price(self, state: EquipmentState) -> dict:
        equipment_list = state.get("equipment_list", "")
        mode = state.get("mode", "light")

        prompt = self._price_prompt(equipment_list, mode)
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        text = response.content

        return {
            "buying_advice": text,
            "price_range": "轻装日徒步约 1000-3000 元，重装多日约 3000-8000 元",
            "lightweight_alternatives": text,
            "step": "priced",
        }

    async def stream_run(self, params: dict):
        """
        流式装备推荐生成器（SSE）
        先逐 token 产出 equipment_list，流完后一次性产出 meta（价格/选购建议等）
        """
        mode = params.get("mode", "light")
        mode_label = "重装徒步（全程背负，需帐篷睡袋炊具等全套露营装备）" if mode == "heavy" else "轻装徒步（沿途有补给住宿，仅需当日装备）"
        days = params.get("days", 1)
        season = params.get("season", "夏")
        terrain = params.get("terrain", "山地")

        equipment_list = ""
        prompt = self._equipment_prompt(mode_label, days, season, terrain)
        async for chunk in self.structured_llm.astream([HumanMessage(content=prompt)]):
            content = getattr(chunk, "content", "")
            if content:
                equipment_list += content
                yield {"type": "token", "content": content}

        # 流完后执行价格评估（一次性 LLM 调用），补齐 meta 字段
        meta = {"mode": mode, "days": days}
        try:
            resp = await self.llm.ainvoke([HumanMessage(content=self._price_prompt(equipment_list, mode))])
            text = resp.content
            meta["buying_advice"] = text
            meta["price_range"] = "轻装日徒步约 1000-3000 元，重装多日约 3000-8000 元"
            meta["lightweight_alternatives"] = text
        except Exception as e:
            logger.error(f"装备价格评估失败: {e}")
            meta["buying_advice"] = ""
            meta["price_range"] = ""
            meta["lightweight_alternatives"] = ""
        yield {"type": "meta", "content": meta}

    async def run(self, params: dict) -> dict:
        compiled = self.compile()
        result = await compiled.ainvoke(params)
        return {
            "mode": result.get("mode", ""),
            "days": result.get("days", 1),
            "equipment_list": result.get("equipment_list", ""),
            "buying_advice": result.get("buying_advice", ""),
            "price_range": result.get("price_range", ""),
            "lightweight_alternatives": result.get("lightweight_alternatives", ""),
        }


_equipment_agent: Optional[EquipmentAgent] = None


def get_equipment_agent() -> EquipmentAgent:
    global _equipment_agent
    if _equipment_agent is None:
        _equipment_agent = EquipmentAgent()
    return _equipment_agent