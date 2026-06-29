"""
路线查询服务模块
通过大模型生成徒步路线结构化数据，辅以联网搜索补充
"""
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.route_cache import RouteCache
from app.utils.llm_client import llm_chat
from app.utils.logger import logger

# 路线缓存有效期（24小时）
ROUTE_CACHE_TTL_HOURS = 24


async def search_routes(keyword: str, db: AsyncSession) -> dict:
    """
    搜索徒步路线，优先从缓存读取
    """
    # 1. 尝试从缓存读取
    cached = await _get_cached_route(keyword, db)
    if cached:
        logger.info(f"路线缓存命中: {keyword}")
        return {
            "keyword": keyword,
            "routes": cached.get("routes", []),
            "llm_summary": cached.get("llm_summary", ""),
            "source": "cache",
        }

    # 2. 通过大模型生成路线数据
    logger.info(f"大模型路线搜索: {keyword}")
    try:
        result = await _generate_routes_by_llm(keyword)
    except Exception as e:
        logger.error(f"大模型路线搜索失败: {e}")
        return {
            "keyword": keyword,
            "routes": [],
            "llm_summary": f"搜索「{keyword}」时遇到问题，请稍后重试。",
            "source": "llm",
        }

    # 3. 写入缓存
    await _cache_route(keyword, result, db)

    return result


async def _get_cached_route(keyword: str, db: AsyncSession) -> dict | None:
    """从数据库缓存获取路线数据"""
    await db.execute(
        delete(RouteCache).where(RouteCache.expires_at < datetime.now(timezone.utc))
    )
    result = await db.execute(
        select(RouteCache)
        .where(RouteCache.keyword == keyword)
        .where(RouteCache.expires_at > datetime.now(timezone.utc))
        .order_by(RouteCache.created_at.desc())
        .limit(1)
    )
    cache_entry = result.scalar_one_or_none()
    if cache_entry:
        return cache_entry.route_data
    return None


async def _cache_route(keyword: str, data: dict, db: AsyncSession) -> None:
    """将路线数据写入缓存"""
    try:
        cache_entry = RouteCache(
            keyword=keyword,
            route_data=data,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ROUTE_CACHE_TTL_HOURS),
        )
        db.add(cache_entry)
        await db.flush()
        logger.info(f"路线缓存写入: {keyword}")
    except Exception as e:
        logger.error(f"路线缓存写入失败: {e}")


async def _generate_routes_by_llm(keyword: str) -> dict:
    """使用大模型生成徒步路线结构化数据"""

    system_prompt = """你是一个专业的中国户外徒步路线数据库。请根据用户输入的关键词，生成该地区最知名的徒步路线信息。

你必须返回严格合法的 JSON 格式，不要包含任何其他文字：

{
  "routes": [
    {
      "name": "路线完整名称",
      "distance": "全程距离，如'15公里'",
      "elevation_gain": "累计爬升，如'1200米'",
      "max_altitude": "最高海拔，如'1918米'",
      "difficulty": "难度等级：简单/中等/困难/专业",
      "duration": "预计耗时，如'2天1夜'或'6-8小时'",
      "best_season": "最佳出行季节，如'5-10月'",
      "summary": "路线轨迹概要，简要描述路线特点、途经点、风景亮点",
      "rating": "综合评分，如'4.5/5'"
    }
  ],
  "llm_summary": "对这些路线的整体分析，包括优缺点对比、适合人群、基础出行注意事项。如果路线涉及高海拔(>3000米)、危险地形等，必须附安全提示。"
}

规则：
1. routes 数组至少包含 2 条路线，最多 5 条
2. 只返回真实存在的知名徒步路线，不要编造不存在的路线
3. 数据要准确，距离、海拔等数字要合理
4. 难度等级要客观
5. summary 字段要包含路线主要特点
6. 如果没有找到匹配的路线，routes 返回空数组，llm_summary 给出建议"""

    user_message = f"请提供关于「{keyword}」的徒步路线信息"

    response = await llm_chat(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=4096,
    )

    # 解析 LLM 返回的 JSON
    try:
        # 尝试直接解析
        data = json.loads(response)
    except json.JSONDecodeError:
        # 尝试从 markdown 代码块中提取
        if "```json" in response:
            start = response.index("```json") + 7
            end = response.index("```", start)
            data = json.loads(response[start:end].strip())
        elif "```" in response:
            start = response.index("```") + 3
            end = response.index("```", start)
            data = json.loads(response[start:end].strip())
        else:
            # 尝试找到 { 开头
            brace_start = response.find("{")
            brace_end = response.rfind("}") + 1
            if brace_start >= 0 and brace_end > brace_start:
                data = json.loads(response[brace_start:brace_end])
            else:
                raise ValueError(f"无法解析 LLM 返回: {response[:200]}")

    routes = data.get("routes", [])
    llm_summary = data.get("llm_summary", "")

    if not routes:
        return {
            "keyword": keyword,
            "routes": [],
            "llm_summary": llm_summary or f"未找到与「{keyword}」相关的知名徒步路线，请尝试其他关键词。",
            "source": "llm",
        }

    return {
        "keyword": keyword,
        "routes": routes,
        "llm_summary": llm_summary,
        "source": "llm",
    }