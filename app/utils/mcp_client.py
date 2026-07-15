"""
MCP 通用客户端模块
支持 SSE 和 streamable_http 两种 MCP 传输协议，用于对接 12306 票务和天气查询服务

MCP Streamable HTTP 协议流程 (2025-03-26):
1. POST initialize → 服务端返回 mcp-session-id header
2. 后续请求携带 mcp-session-id header
"""
import json
from typing import Any, Optional
import httpx
from app.core.config import get_settings
from app.utils.logger import logger

settings = get_settings()


def _mcp_http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """构建带代理的 httpx 客户端"""
    proxy = settings.https_proxy or settings.http_proxy
    return httpx.AsyncClient(proxy=proxy, timeout=timeout) if proxy else httpx.AsyncClient(timeout=timeout)


class MCPClient:
    """MCP 通用客户端，封装 JSON-RPC 2.0 协议，支持 session 管理"""

    def __init__(self, service_type: str, service_url: str):
        """
        Args:
            service_type: 传输协议类型 ("sse" | "streamable_http")
            service_url: MCP 服务端点 URL
        """
        self.service_type = service_type
        self.service_url = service_url
        self._request_id = 0
        self._session_id: Optional[str] = None

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _reset_session(self) -> None:
        """重置 session，下次请求会重新初始化"""
        self._session_id = None

    async def _ensure_session(self) -> None:
        """确保已建立 MCP session（仅 streamable_http 需要）"""
        if self._session_id is not None or self.service_type != "streamable_http":
            return

        try:
            async with _mcp_http_client(timeout=15.0) as client:
                response = await client.post(
                    self.service_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": self._next_id(),
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "outdoor-buddy", "version": "1.0.0"},
                        },
                    },
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                session_id = response.headers.get("mcp-session-id")
                if session_id:
                    self._session_id = session_id
                    logger.info(f"MCP session 已建立: {session_id[:8]}...")
                else:
                    logger.warning("MCP 响应中未找到 mcp-session-id header")
        except Exception as e:
            logger.error(f"MCP session 初始化失败: {e}")
            raise

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        调用 MCP 工具
        Args:
            tool_name: 工具名称
            arguments: 工具参数
        Returns:
            工具返回的数据
        """
        if self.service_type == "sse":
            return await self._call_sse(tool_name, arguments)
        elif self.service_type == "streamable_http":
            return await self._call_streamable_http(tool_name, arguments)
        else:
            raise ValueError(f"不支持的 MCP 传输协议: {self.service_type}")

    async def _call_streamable_http(self, tool_name: str, arguments: dict, _retry: bool = True) -> dict:
        """通过 streamable_http 协议调用 MCP 工具，session 过期自动重试一次"""
        await self._ensure_session()

        request_payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        headers = {"Content-Type": "application/json"}
        if self._session_id:
            headers["mcp-session-id"] = self._session_id

        try:
            async with _mcp_http_client(timeout=60.0) as client:
                response = await client.post(
                    self.service_url,
                    json=request_payload,
                    headers=headers,
                )
                # 400 通常是 session 过期，重置 session 并重试一次
                if _retry and response.status_code == 400:
                    logger.warning("MCP 返回 400，可能 session 过期，重新连接...")
                    self._reset_session()
                    return await self._call_streamable_http(tool_name, arguments, _retry=False)

                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"MCP streamable_http 调用失败 [{tool_name}]: {e}")
            raise
        except Exception as e:
            logger.error(f"MCP 调用异常 [{tool_name}]: {e}")
            raise

    async def _call_sse(self, tool_name: str, arguments: dict) -> dict:
        """
        通过 SSE 协议调用 MCP 工具
        采用简化的 SSE 交互流程：发送 JSON-RPC 请求，流式接收响应
        """
        request_payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        try:
            async with _mcp_http_client(timeout=30.0) as client:
                response = await client.post(
                    self.service_url,
                    json=request_payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                )
                response.raise_for_status()

                # 解析 SSE 响应
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" in content_type:
                    return self._parse_sse_response(response.text)
                else:
                    # 普通 JSON 响应
                    return response.json()
        except httpx.HTTPError as e:
            logger.warning(f"MCP SSE 调用失败 [{tool_name}]: {e}")
            raise
        except Exception as e:
            logger.warning(f"MCP 调用异常 [{tool_name}]: {e}")
            raise

    async def list_tools(self) -> list[dict]:
        """列出 MCP 服务提供的所有工具"""
        if self.service_type == "streamable_http":
            return await self._list_tools_streamable_http()
        else:
            return await self._list_tools_sse()

    async def _list_tools_streamable_http(self, _retry: bool = True) -> list[dict]:
        """通过 streamable_http 列出工具，session 过期自动重试一次"""
        await self._ensure_session()

        headers = {"Content-Type": "application/json"}
        if self._session_id:
            headers["mcp-session-id"] = self._session_id

        try:
            async with _mcp_http_client(timeout=15.0) as client:
                response = await client.post(
                    self.service_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": self._next_id(),
                        "method": "tools/list",
                        "params": {},
                    },
                    headers=headers,
                )
                if _retry and response.status_code == 400:
                    logger.warning("list_tools 返回 400，可能 session 过期，重新连接...")
                    self._reset_session()
                    return await self._list_tools_streamable_http(_retry=False)

                response.raise_for_status()
                result = response.json()
                return result.get("result", {}).get("tools", [])
        except Exception as e:
            logger.error(f"MCP 工具列表获取失败: {e}")
            return []

    async def _list_tools_sse(self) -> list[dict]:
        """通过 SSE 列出工具"""
        try:
            async with _mcp_http_client(timeout=15.0) as client:
                response = await client.post(
                    self.service_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": self._next_id(),
                        "method": "tools/list",
                        "params": {},
                    },
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                result = response.json()
                return result.get("result", {}).get("tools", [])
        except Exception as e:
            logger.error(f"MCP 工具列表获取失败: {e}")
            return []

    def _parse_sse_response(self, text: str) -> dict:
        """解析 SSE 格式的响应文本"""
        result = {}
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str and data_str != "[DONE]":
                    try:
                        data = json.loads(data_str)
                        if "result" in data:
                            result = data["result"]
                        elif "error" in data:
                            logger.error(f"MCP SSE 错误: {data['error']}")
                    except json.JSONDecodeError:
                        continue
        return result


# 全局 MCP 客户端单例
_ticket_client: Optional[MCPClient] = None
_weather_client: Optional[MCPClient] = None


def get_ticket_mcp_client() -> MCPClient:
    """获取 12306 票务 MCP 客户端"""
    global _ticket_client
    if _ticket_client is None:
        _ticket_client = MCPClient(
            service_type=settings.mcp_12306_type,
            service_url=settings.mcp_12306_url,
        )
        logger.info("12306 MCP 客户端初始化完成")
    return _ticket_client


def get_weather_mcp_client() -> MCPClient:
    """获取天气 MCP 客户端"""
    global _weather_client
    if _weather_client is None:
        _weather_client = MCPClient(
            service_type=settings.mcp_weather_type,
            service_url=settings.mcp_weather_url,
        )
        logger.info("天气 MCP 客户端初始化完成")
    return _weather_client
