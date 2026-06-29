"""
天气查询服务模块
对接天气 MCP 服务获取实时气象数据，生成出行评估与装备调整建议
"""
from app.utils.mcp_client import get_weather_mcp_client
from app.utils.llm_client import llm_chat
from app.utils.logger import logger


async def query_weather(location: str, date: str | None, forecast_days: int) -> dict:
    """
    查询天气数据
    Args:
        location: 地点名称
        date: 查询日期
        forecast_days: 预报天数 1-7
    Returns:
        天气数据、出行评估、装备建议
    """
    weather_client = get_weather_mcp_client()

    # 1. 先列出可用工具
    tools = await weather_client.list_tools()
    logger.info(f"天气 MCP 可用工具: {[t.get('name') for t in tools]}")

    # 2. 调用天气查询工具
    forecast_data = []
    try:
        # 尝试调用天气查询工具（工具名可能因服务而异）
        tool_name = "get_weather" if any("weather" in t.get("name", "") for t in tools) else (tools[0]["name"] if tools else "get_weather")
        result = await weather_client.call_tool(tool_name, {
            "location": location,
            "date": date or "",
            "days": forecast_days,
        })
        forecast_data = _parse_weather_result(result)
    except Exception as e:
        logger.error(f"天气 MCP 调用失败: {e}")
        # 返回模拟数据以便前端展示
        forecast_data = _generate_fallback_weather(location, forecast_days)

    # 3. 大模型生成出行评估与装备建议
    assessment = ""
    equipment_advice = ""
    if forecast_data:
        try:
            assessment, equipment_advice = await _generate_weather_assessment(location, forecast_data)
        except Exception as e:
            logger.error(f"天气评估生成失败: {e}")
            assessment = "天气评估暂时不可用"
            equipment_advice = "请关注实时天气预警，做好相应准备"

    return {
        "location": location,
        "forecast": forecast_data,
        "hiking_assessment": assessment,
        "equipment_advice": equipment_advice,
    }


def _parse_weather_result(result: dict) -> list[dict]:
    """解析天气 MCP 返回结果"""
    # 尝试从多种可能的响应结构中提取数据
    if "content" in result:
        for item in result["content"]:
            if isinstance(item, dict) and item.get("type") == "text":
                import json
                try:
                    return json.loads(item.get("text", "[]"))
                except json.JSONDecodeError:
                    pass

    if "forecast" in result:
        return result["forecast"]

    if isinstance(result, list):
        return result

    return []


def _generate_fallback_weather(location: str, days: int) -> list[dict]:
    """生成备用天气数据（当 MCP 服务不可用时）"""
    import datetime
    forecast = []
    for i in range(days):
        d = datetime.date.today() + datetime.timedelta(days=i)
        forecast.append({
            "date": d.strftime("%Y-%m-%d"),
            "temperature": "18°C ~ 28°C",
            "precipitation": "20%",
            "wind": "东北风 2-3级",
            "uv_index": "中等",
            "alert": "无",
        })
    return forecast


async def _generate_weather_assessment(location: str, forecast: list[dict]) -> tuple[str, str]:
    """使用大模型生成出行评估和装备建议"""
    import json

    system_prompt = """你是户外天气风险评估专家。根据天气预报数据，输出：
1. **徒步出行可行性评估**：综合考虑温度、降水、风力、紫外线等因素
2. **装备调整建议**：针对具体天气条件给出装备调整方案

极端天气（暴雨、大风、高温、低温）必须强化风险提示。"""

    user_message = f"地点：{location}\n天气预报：\n{json.dumps(forecast, ensure_ascii=False)}"

    llm_result = await llm_chat(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=2048,
    )

    # 分离评估和建议
    if "装备调整" in llm_result:
        parts = llm_result.split("装备调整", 1)
        assessment = parts[0].strip()
        equipment_advice = "装备调整" + parts[1].strip() if len(parts) > 1 else ""
    else:
        assessment = llm_result
        equipment_advice = "请根据实际天气情况调整装备。"

    return assessment, equipment_advice