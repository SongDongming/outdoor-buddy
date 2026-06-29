"""
天气查询 Agent
LangGraph 图: 获取真实天气 → 评估风险 → 生成建议
数据源: Open-Meteo (主) → wttr.in (备) — 均为免费真实数据
"""
import datetime
import json as _json
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
import httpx
from app.agents.base import AgentBase, create_llm, _build_async_http_client
from app.utils.logger import logger


class WeatherState(TypedDict, total=False):
    location: str
    date: str | None
    forecast_days: int
    forecast: list
    hiking_assessment: str
    equipment_advice: str
    step: str
    error: Optional[str]


# 常用中国地名 → 经纬度 (优先快速匹配，减少 LLM 调用)
LOCATION_COORDS = {
    # 山脉 / 徒步目的地
    "武功山": (27.47, 114.17), "黄山": (30.13, 118.17), "泰山": (36.25, 117.10),
    "华山": (34.48, 110.08), "峨眉山": (29.59, 103.48), "四姑娘山": (31.10, 102.90),
    "雨崩": (28.39, 98.87), "虎跳峡": (27.19, 100.08), "稻城亚丁": (28.45, 100.35),
    "梅里雪山": (28.43, 98.68), "五台山": (39.00, 113.58), "长白山": (42.00, 128.05),
    "张家界": (29.33, 110.48), "九寨沟": (33.25, 103.90), "太白山": (33.95, 107.77),
    "庐山": (29.56, 115.98), "三清山": (28.91, 118.06), "武夷山": (27.72, 117.68),
    "贡嘎山": (29.59, 101.88), "哈巴雪山": (27.33, 100.10), "南太行": (35.51, 113.58),
    "太行山": (36.00, 113.70), "秦岭": (33.90, 108.50), "大别山": (31.20, 115.50),
    "雁荡山": (28.37, 121.06), "普陀山": (30.00, 122.39), "武当山": (32.40, 111.00),
    "青城山": (30.90, 103.57), "崂山": (36.20, 120.62), "恒山": (39.67, 113.72),
    "衡山": (27.23, 112.75), "嵩山": (34.50, 112.93),
    # 主要城市
    "北京": (39.90, 116.40), "上海": (31.23, 121.47), "广州": (23.13, 113.26),
    "深圳": (22.54, 114.06), "杭州": (30.25, 120.16), "成都": (30.57, 104.07),
    "重庆": (29.56, 106.55), "武汉": (30.59, 114.30), "南京": (32.06, 118.80),
    "西安": (34.26, 108.94), "昆明": (25.04, 102.70), "长沙": (28.23, 112.94),
    "南昌": (28.68, 115.86), "贵阳": (26.65, 106.63), "拉萨": (29.65, 91.10),
    "丽江": (26.86, 100.23), "大理": (25.61, 100.27), "香格里拉": (27.83, 99.70),
    "萍乡": (27.62, 113.85), "天津": (39.13, 117.20), "沈阳": (41.80, 123.43),
    "哈尔滨": (45.75, 126.63), "长春": (43.88, 125.32), "济南": (36.67, 116.98),
    "郑州": (34.76, 113.65), "合肥": (31.82, 117.23), "福州": (26.07, 119.30),
    "南宁": (22.82, 108.37), "海口": (20.02, 110.35), "兰州": (36.06, 103.83),
    "西宁": (36.62, 101.78), "银川": (38.47, 106.27), "乌鲁木齐": (43.83, 87.62),
    "呼和浩特": (40.83, 111.75), "石家庄": (38.05, 114.50), "太原": (37.87, 112.55),
    "苏州": (31.30, 120.62), "无锡": (31.57, 120.30), "宁波": (29.87, 121.55),
    "青岛": (36.07, 120.38), "大连": (38.91, 121.61), "厦门": (24.49, 118.10),
    "珠海": (22.27, 113.58), "三亚": (18.25, 109.50), "桂林": (25.27, 110.28),
    "洛阳": (34.62, 112.45), "开封": (34.80, 114.30), "宜昌": (30.70, 111.28),
    "新乡": (35.30, 113.93), "焦作": (35.24, 113.23), "晋城": (35.49, 112.85),
}


class WeatherAgent(AgentBase):
    """天气查询 Agent — 双真实数据源"""

    def __init__(self):
        super().__init__(name="WeatherAgent", temperature=0.5)
        self.assess_llm = create_llm(temperature=0.4, max_tokens=2048)

    def build_graph(self):
        workflow = StateGraph(WeatherState)
        workflow.add_node("fetch_weather", self._fetch_node)
        workflow.add_node("assess_risk", self._assess_node)
        workflow.set_entry_point("fetch_weather")
        workflow.add_edge("fetch_weather", "assess_risk")
        workflow.add_edge("assess_risk", END)
        self.graph = workflow

    async def _fetch_node(self, state: WeatherState) -> dict:
        location = state.get("location", "")
        forecast_days = min(state.get("forecast_days", 7), 7)
        forecast = await self._fetch_weather(location, forecast_days)
        return {"forecast": forecast, "step": "fetched"}

    # ==================== 数据获取主流程 ====================

    async def _fetch_weather(self, location: str, days: int) -> list:
        """
        双源策略获取真实天气:
        1. Open-Meteo (主) — 全球覆盖，结构化数据，无需 Key
        2. wttr.in (备) — 全球覆盖，无需 Key，直接按地名查询
        """
        # --- 源 1: Open-Meteo ---
        forecast = await self._try_open_meteo(location, days)
        if forecast:
            return forecast

        # --- 源 2: wttr.in ---
        forecast = await self._try_wttr_in(location, days)
        if forecast:
            return forecast

        # --- 都不行 ---
        logger.error(f"[Weather] 所有数据源均无法访问，请检查网络")
        raise RuntimeError(f"无法获取「{location}」的天气数据，请稍后重试")

    # ==================== 源 1: Open-Meteo ====================

    async def _try_open_meteo(self, location: str, days: int) -> list | None:
        """尝试从 Open-Meteo 获取数据，失败返回 None"""
        coords = self._resolve_coords(location)
        if not coords:
            coords = await self._geocode_by_llm(location)
            if not coords:
                logger.warning(f"[Weather] 无法解析 '{location}' 的坐标")
                return None

        lat, lon = coords
        logger.info(f"[Weather] Open-Meteo: {location} ({lat:.4f}, {lon:.4f}), {days}天")

        try:
            params = (
                f"latitude={lat}&longitude={lon}"
                f"&daily=temperature_2m_max,temperature_2m_min"
                f",precipitation_probability_max"
                f",wind_speed_10m_max,wind_direction_10m_dominant"
                f",uv_index_max"
                f"&timezone=Asia/Shanghai"
                f"&forecast_days={days}"
            )
            url = f"https://api.open-meteo.com/v1/forecast?{params}"

            async with _build_async_http_client(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            daily = data.get("daily", {})
            if not daily.get("time"):
                logger.warning("[Weather] Open-Meteo 返回空数据")
                return None

            forecast = self._parse_open_meteo(daily, days)
            logger.info(f"[Weather] Open-Meteo 成功: {len(forecast)} 天")
            return forecast

        except httpx.TimeoutException as e:
            logger.warning(f"[Weather] Open-Meteo 超时: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"[Weather] Open-Meteo HTTP {e.response.status_code}")
            return None
        except Exception as e:
            logger.warning(f"[Weather] Open-Meteo 异常: {type(e).__name__}: {e}")
            return None

    def _parse_open_meteo(self, daily: dict, days: int) -> list:
        """解析 Open-Meteo 响应"""
        forecast = []
        times = daily.get("time", [])
        tmaxs = daily.get("temperature_2m_max", [])
        tmins = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_probability_max", [])
        winds = daily.get("wind_speed_10m_max", [])
        windds = daily.get("wind_direction_10m_dominant", [])
        uvs = daily.get("uv_index_max", [])

        for i in range(min(days, len(times))):
            wind_label = self._wind_label(windds[i]) if i < len(windds) else "--"
            alert = ""
            p = precip[i] if i < len(precip) else 0
            w = winds[i] if i < len(winds) else 0
            u = uvs[i] if i < len(uvs) else 0
            if p > 70:
                alert = "暴雨预警"
            elif w > 30:
                alert = "大风预警"
            elif u > 8:
                alert = "强紫外线"

            forecast.append({
                "date": str(times[i]) if i < len(times) else "",
                "temperature": f"{tmins[i] if i < len(tmins) else '--'}°C ~ {tmaxs[i] if i < len(tmaxs) else '--'}°C",
                "precipitation": f"{p}%",
                "wind": f"{wind_label} {w}km/h",
                "uv_index": self._uv_label(u),
                "alert": alert or "无",
                "source": "Open-Meteo",
            })
        return forecast

    # ==================== 源 2: wttr.in ====================

    async def _try_wttr_in(self, location: str, days: int) -> list | None:
        """尝试从 wttr.in 获取数据，失败返回 None"""
        logger.info(f"[Weather] wttr.in: {location}, {days}天")

        try:
            url = f"https://wttr.in/{location}?format=j1"
            async with _build_async_http_client(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            weather_list = data.get("weather", [])
            if not weather_list:
                logger.warning("[Weather] wttr.in 返回空数据")
                return None

            forecast = self._parse_wttr_in(weather_list, days)
            logger.info(f"[Weather] wttr.in 成功: {len(forecast)} 天")
            return forecast

        except httpx.TimeoutException as e:
            logger.warning(f"[Weather] wttr.in 超时: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"[Weather] wttr.in HTTP {e.response.status_code}")
            return None
        except Exception as e:
            logger.warning(f"[Weather] wttr.in 异常: {type(e).__name__}: {e}")
            return None

    def _parse_wttr_in(self, weather_list: list, days: int) -> list:
        """解析 wttr.in 响应"""
        forecast = []
        for day_data in weather_list[:days]:
            date = day_data.get("date", "")
            maxtemp = day_data.get("maxtempC", "--")
            mintemp = day_data.get("mintempC", "--")

            # 取当天中午时间段的详细数据
            hourly = day_data.get("hourly", [])
            precip = "0%"
            wind_label = "--"
            wind_speed = "0"
            uv = 0
            if hourly:
                mid = hourly[min(len(hourly) // 2, len(hourly) - 1)]
                precip = f"{mid.get('chanceofrain', '0')}%"
                wind_label = mid.get("winddir16Point", "--")
                wind_speed = mid.get("windspeedKmph", "0")
                uv = int(mid.get("uvIndex", 0) or 0)

            alert = ""
            precip_val = int(precip.replace("%", "") or "0")
            wind_val = int(wind_speed or "0")
            if precip_val > 70:
                alert = "暴雨预警"
            elif wind_val > 30:
                alert = "大风预警"
            elif uv > 8:
                alert = "强紫外线"

            forecast.append({
                "date": str(date),
                "temperature": f"{mintemp}°C ~ {maxtemp}°C",
                "precipitation": precip,
                "wind": f"{wind_label} {wind_speed}km/h",
                "uv_index": self._uv_label(uv),
                "alert": alert or "无",
                "source": "wttr.in",
            })
        return forecast

    # ==================== 地理位置解析 ====================

    def _resolve_coords(self, location: str) -> tuple | None:
        """精确/模糊匹配内置坐标库"""
        if location in LOCATION_COORDS:
            return LOCATION_COORDS[location]
        for name, c in LOCATION_COORDS.items():
            if name in location or location in name:
                return c
        return None

    async def _geocode_by_llm(self, location: str) -> tuple | None:
        """用大模型推断任意地名的经纬度"""
        try:
            prompt = (
                f'请返回「{location}」的经纬度坐标，仅输出 JSON: '
                f'{{"lat": 数字, "lon": 数字, "name": "地点名"}}'
            )
            resp = await self.llm.ainvoke([HumanMessage(content=prompt)])
            text = resp.content.strip()
            # 清理 markdown
            if "```" in text:
                text = text.split("```")[1].replace("json", "").strip()
            data = _json.loads(text)
            lat = float(data.get("lat", 0))
            lon = float(data.get("lon", 0))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                logger.info(f"[Weather] LLM 解析坐标: {location} → ({lat}, {lon})")
                return (lat, lon)
        except Exception as e:
            logger.warning(f"[Weather] LLM 坐标解析失败: {e}")
        return None

    # ==================== 工具方法 ====================

    def _wind_label(self, deg: int) -> str:
        dirs = ["北风", "东北风", "东风", "东南风", "南风", "西南风", "西风", "西北风"]
        idx = round(deg / 45) % 8
        return dirs[idx]

    def _uv_label(self, uv: float) -> str:
        if uv <= 2: return "低"
        if uv <= 5: return "中等"
        if uv <= 7: return "高"
        if uv <= 10: return "很高"
        return "极高"

    # ==================== 风险评估 ====================

    async def _assess_node(self, state: WeatherState) -> dict:
        location = state.get("location", "")
        forecast = state.get("forecast", [])

        if not forecast:
            return {"hiking_assessment": "天气数据获取失败", "equipment_advice": "", "step": "assessed"}

        prompt = (
            f"地点：{location}，天气：{_json.dumps(forecast, ensure_ascii=False)[:1500]}。"
            f"生成：1.徒步出行可行性评估 2.装备调整建议。极端天气必须强化风险提示。"
        )

        try:
            response = await self.assess_llm.ainvoke([
                SystemMessage(content="你是户外天气风险评估专家。"),
                HumanMessage(content=prompt)
            ])
            text = response.content
        except Exception as e:
            logger.error(f"[Weather] LLM评估失败: {e}")
            text = "天气评估暂时不可用，请根据预报数据自行判断。"

        if "装备调整" in text:
            parts = text.split("装备调整", 1)
            return {
                "hiking_assessment": parts[0].strip(),
                "equipment_advice": ("装备调整" + parts[1].strip()) if len(parts) > 1 else "",
                "step": "assessed",
            }

        return {
            "hiking_assessment": text,
            "equipment_advice": "请根据实际天气调整装备。",
            "step": "assessed",
        }

    async def run(self, location: str, date: str = None, forecast_days: int = 7) -> dict:
        compiled = self.compile()
        result = await compiled.ainvoke({
            "location": location, "date": date, "forecast_days": forecast_days
        })
        return {
            "location": location,
            "forecast": result.get("forecast", []),
            "hiking_assessment": result.get("hiking_assessment", ""),
            "equipment_advice": result.get("equipment_advice", ""),
        }


_weather_agent: Optional[WeatherAgent] = None


def get_weather_agent() -> WeatherAgent:
    global _weather_agent
    if _weather_agent is None:
        _weather_agent = WeatherAgent()
    return _weather_agent
