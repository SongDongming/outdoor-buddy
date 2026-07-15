"""
交通票务查询服务模块
对接 12306 MCP 服务（SSE 协议），查询火车票信息
"""
from app.utils.mcp_client import get_ticket_mcp_client
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
    error_msg = ""
    try:
        tool_name = "query-tickets" if any("query-ticket" in t.get("name", "") for t in tools) else (tools[0]["name"] if tools else "query-tickets")
        result = await ticket_client.call_tool(tool_name, {
            "from_station": from_city,
            "to_station": to_city,
            "train_date": date,
        })
        tickets = _parse_ticket_result(result)
        if not tickets:
            error_msg = "未查询到符合条件车次，请尝试调整日期或城市"
    except Exception as e:
        logger.error(f"12306 MCP 调用失败: {e}")
        error_msg = f"12306 票务服务当前不可用，请稍后重试"

    return {
        "from_city": from_city,
        "to_city": to_city,
        "date": date,
        "tickets": tickets,
        "transfer_advice": "",
        "travel_time_advice": "",
        "error_msg": error_msg,
    }


def _parse_ticket_result(result: dict) -> list[dict]:
    """
    解析票务 MCP 返回结果，统一为内部格式

    MCP JSON-RPC 响应结构:
    {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": "{...}"}]}}
    或简化:
    {"content": [{"type": "text", "text": "{...}"}]}
    """
    import json

    # 先剥离 JSON-RPC 外层 result 字段
    inner = result.get("result", result)

    raw_data = None

    # 1. MCP content 格式: {"content": [{"type": "text", "text": "{...}"}]}
    if "content" in inner:
        for item in inner["content"]:
            if isinstance(item, dict) and item.get("type") == "text":
                try:
                    raw_data = json.loads(item.get("text", "{}"))
                except json.JSONDecodeError:
                    pass
                break

    # 2. 内层直接就是数据
    if raw_data is None and "trains" in inner:
        raw_data = inner

    # 3. 顶层 tickets 字段
    if raw_data is None and "tickets" in result:
        return result["tickets"]

    # 4. 本身就是列表
    if raw_data is None and isinstance(result, list):
        return result

    if raw_data is None:
        return []

    # 如果是列表，直接返回
    if isinstance(raw_data, list):
        return raw_data

    # 提取 trains 列表（mcp-server-12306 格式: {"success": true, "trains": [...]}）
    trains = raw_data.get("trains", [])
    if not trains:
        return []

    # 转换 mcp-server-12306 格式 → 内部格式
    parsed = []
    for t in trains:
        seats = t.get("seats", {})
        seat_parts = []
        seat_labels = {
            "business": "商务座", "first_class": "一等座", "second_class": "二等座",
            "soft_sleeper": "软卧", "hard_sleeper": "硬卧", "hard_seat": "硬座", "no_seat": "无座",
        }
        for key, label in seat_labels.items():
            val = seats.get(key)
            if val and val != "无":
                seat_parts.append(f"{label} {val}")

        has_tickets = any(v and v != "无" for v in seats.values())
        status = "有票" if has_tickets else "售罄"

        parsed.append({
            "train_no": t.get("train_no", ""),
            "from_station": t.get("from_station", ""),
            "to_station": t.get("to_station", ""),
            "departure_time": t.get("start_time", ""),
            "arrival_time": t.get("arrive_time", ""),
            "duration": t.get("duration", ""),
            "seat_types": " / ".join(seat_parts) if seat_parts else "信息暂无",
            "status": status,
        })

    return parsed


