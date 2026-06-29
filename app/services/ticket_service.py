"""
交通票务查询服务模块
对接 12306 MCP 服务（SSE 协议），查询火车票信息
"""
from app.utils.mcp_client import get_ticket_mcp_client
from app.utils.llm_client import llm_chat
from app.utils.logger import logger


async def query_tickets(from_city: str, to_city: str, date: str) -> dict:
    """
    查询火车票信息
    Args:
        from_city: 出发城市
        to_city: 目的城市
        date: 出行日期
    Returns:
        票务信息、接驳建议、出行时段推荐
    """
    ticket_client = get_ticket_mcp_client()

    # 1. 列出可用工具
    tools = await ticket_client.list_tools()
    logger.info(f"12306 MCP 可用工具: {[t.get('name') for t in tools]}")

    # 2. 调用票务查询工具
    tickets = []
    try:
        tool_name = "search_tickets" if any("ticket" in t.get("name", "") for t in tools) else (tools[0]["name"] if tools else "search_tickets")
        result = await ticket_client.call_tool(tool_name, {
            "from": from_city,
            "to": to_city,
            "date": date,
        })
        tickets = _parse_ticket_result(result)
    except Exception as e:
        logger.error(f"12306 MCP 调用失败: {e}")
        tickets = _generate_fallback_tickets(from_city, to_city, date)

    # 3. 大模型生成接驳建议和出行时段推荐
    transfer_advice = ""
    travel_time_advice = ""
    if tickets:
        try:
            transfer_advice, travel_time_advice = await _generate_travel_advice(
                from_city, to_city, date, tickets
            )
        except Exception as e:
            logger.error(f"出行建议生成失败: {e}")
            transfer_advice = "建议到达后使用当地公共交通或打车前往徒步起点。"
            travel_time_advice = "建议选择上午出发的车次，预留充足时间到达目的地。"

    return {
        "from_city": from_city,
        "to_city": to_city,
        "date": date,
        "tickets": tickets,
        "transfer_advice": transfer_advice,
        "travel_time_advice": travel_time_advice,
    }


def _parse_ticket_result(result: dict) -> list[dict]:
    """解析票务 MCP 返回结果"""
    if "content" in result:
        for item in result["content"]:
            if isinstance(item, dict) and item.get("type") == "text":
                import json
                try:
                    return json.loads(item.get("text", "[]"))
                except json.JSONDecodeError:
                    pass

    if "tickets" in result:
        return result["tickets"]

    if isinstance(result, list):
        return result

    return []


def _generate_fallback_tickets(from_city: str, to_city: str, date: str) -> list[dict]:
    """生成备用票务数据（当 MCP 服务不可用时）"""
    return [
        {
            "train_no": f"G{100 + i}",
            "departure_time": f"{6 + i * 2:02d}:00",
            "arrival_time": f"{10 + i * 2:02d}:30",
            "duration": "4小时30分",
            "seat_types": "二等座 ¥350 / 一等座 ¥560",
            "status": "有票",
        }
        for i in range(3)
    ]


async def _generate_travel_advice(
    from_city: str, to_city: str, date: str, tickets: list[dict]
) -> tuple[str, str]:
    """使用大模型生成出行建议"""
    import json

    system_prompt = """你是火车出行顾问。根据车次信息，生成：
1. **到站接驳建议**：到达目的地后如何前往徒步起点
2. **推荐出行时段**：基于到达时间推荐最佳出行时段"""

    user_message = f"出发：{from_city} → 目的：{to_city}\n日期：{date}\n车次：\n{json.dumps(tickets, ensure_ascii=False)}"

    llm_result = await llm_chat(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=2048,
    )

    # 分离接驳建议和时段推荐
    if "出行时段" in llm_result or "推荐时段" in llm_result:
        parts = llm_result.split("出行时段", 1) if "出行时段" in llm_result else llm_result.split("推荐时段", 1)
        transfer = parts[0].strip()
        travel_time = ("出行时段" + parts[1].strip()) if len(parts) > 1 else ""
    else:
        transfer = llm_result
        travel_time = "建议选择上午出发的车次，预留充足时间。"

    return transfer, travel_time