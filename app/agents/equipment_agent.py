"""
装备推荐 Agent —— 根据徒步模式/天数/季节/地形生成装备清单，并评估预算。

图结构（一条线性流水线，无分支，顺序执行三个节点）：
    analyze_params ──> generate_equipment ──> estimate_price ──> END

相比 route_agent 的「条件分叉」，这里是最简单的顺序图，适合作为理解 LangGraph 的入门。
"""
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage
from app.agents.base import AgentBase, create_llm
from app.utils.logger import logger


class EquipmentState(TypedDict, total=False):
    """装备 Agent 的状态。上半部分是输入参数，下半部分是各节点产出的结果。"""
    mode: str            # 徒步模式：light(轻装) / heavy(重装)
    days: int            # 天数
    season: str          # 季节
    terrain: str         # 地形
    people_count: int
    # 以下为各节点产出
    equipment_list: str              # 生成的装备清单
    buying_advice: str               # 选购建议
    price_range: str                 # 价格区间
    lightweight_alternatives: str    # 轻量化替代方案
    step: str
    error: Optional[str]


class EquipmentAgent(AgentBase):
    """装备推荐 Agent"""

    def __init__(self):
        super().__init__(name="EquipmentAgent", temperature=0.5)
        # 生成装备清单用更低的温度，让输出更稳定、更像「标准清单」
        self.structured_llm = create_llm(temperature=0.3, max_tokens=4096)

    def build_graph(self):
        """构建线性流水线：三个节点首尾相接，无分支。"""
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
        """
        参数解析节点：这一步不调 LLM，只是把简短的 mode 代码（light/heavy）
        翻译成给 LLM 看的、语义完整的描述文字，供后续节点拼进提示词。
        """
        mode = state.get("mode", "light")
        mode_label = "重装徒步（全程背负，需帐篷睡袋炊具等全套露营装备）" if mode == "heavy" else "轻装徒步（沿途有补给住宿，仅需当日装备）"
        return {"mode": mode, "mode_label": mode_label, "step": "analyzed"}

    @staticmethod
    def _equipment_prompt(mode_label: str, days: int, season: str, terrain: str) -> str:
        """
        生成装备清单的提示词（纯函数，流式/非流式两条路径共用，
        保证两种模式下的输出质量一致）。
        """
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
        """装备生成节点：调用 LLM 产出装备清单文本。"""
        mode_label = state.get("mode_label", "")
        days = state.get("days", 1)
        season = state.get("season", "夏")
        terrain = state.get("terrain", "山地")

        prompt = self._equipment_prompt(mode_label, days, season, terrain)
        response = await self.structured_llm.ainvoke([HumanMessage(content=prompt)])
        return {"equipment_list": response.content, "step": "generated"}

    async def _estimate_price(self, state: EquipmentState) -> dict:
        """
        价格评估节点：基于上一步的装备清单，用主 LLM 再评估预算和选购建议。
        注意这是「串联」的第二次 LLM 调用——它依赖 _generate_equipment 的结果，
        所以只能顺序执行，不能并行。
        """
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
        流式装备推荐生成器（SSE，前端逐字显示）。
        三段式输出协议：
          1. {type:"token"}  —— 逐 token 推送装备清单正文
          2. {type:"done"}   —— 清单流完，通知前端结束「生成中」加载态
          3. {type:"meta"}   —— 价格/选购建议等（第二次 LLM 调用，一次性返回）

        注意：这里用 astream（流式）而非 ainvoke（一次性），是 SSE 逐字显示的关键。
        """
        mode = params.get("mode", "light")
        mode_label = "重装徒步（全程背负，需帐篷睡袋炊具等全套露营装备）" if mode == "heavy" else "轻装徒步（沿途有补给住宿，仅需当日装备）"
        days = params.get("days", 1)
        season = params.get("season", "夏")
        terrain = params.get("terrain", "山地")

        equipment_list = ""
        prompt = self._equipment_prompt(mode_label, days, season, terrain)
        # astream 返回异步迭代器，每个 chunk 是模型生成的一小段文字
        async for chunk in self.structured_llm.astream([HumanMessage(content=prompt)]):
            content = getattr(chunk, "content", "")
            if content:
                equipment_list += content
                yield {"type": "token", "content": content}

        # 内容流完立即通知前端结束"生成中"加载，避免连接挂起
        yield {"type": "done"}

        # 价格评估（一次性 LLM 调用）带 30s 超时，失败不阻塞、补齐空 meta
        import asyncio
        meta = {"mode": mode, "days": days}
        try:
            resp = await asyncio.wait_for(
                self.llm.ainvoke([HumanMessage(content=self._price_prompt(equipment_list, mode))]),
                timeout=30,
            )
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
        """对外入口（非流式）：一次跑完整张图，返回整理好的结果字典。"""
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


# 全局单例：进程内只创建一次 EquipmentAgent（图只编译一次）
_equipment_agent: Optional[EquipmentAgent] = None


def get_equipment_agent() -> EquipmentAgent:
    """获取 EquipmentAgent 单例"""
    global _equipment_agent
    if _equipment_agent is None:
        _equipment_agent = EquipmentAgent()
    return _equipment_agent