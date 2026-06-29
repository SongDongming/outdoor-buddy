"""
装备查询与推荐服务模块
实现装备检索、联网搜索、重装/轻装推荐逻辑
"""
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.equipment_cache import EquipmentCache
from app.utils.scraper import fetch_page, parse_html
from app.utils.llm_client import llm_chat
from app.utils.logger import logger

# 装备缓存有效期（24小时）
EQUIPMENT_CACHE_TTL_HOURS = 24


async def search_equipment(
    keyword: str,
    category: str | None,
    db: AsyncSession,
) -> dict:
    """
    装备查询：检索→联网搜索→LLM整理→缓存
    """
    # 1. 检查缓存
    cache_key = f"{keyword}_{category or 'all'}"
    cached = await _get_cached_equipment(cache_key, db)
    if cached:
        logger.info(f"装备缓存命中: {cache_key}")
        return cached

    # 2. 联网搜索（模拟：通过搜索电商平台公开信息）
    equipment_data = await _fetch_equipment_data(keyword, category)

    # 3. LLM 整理
    if equipment_data:
        try:
            enriched = await _enrich_equipment_data(keyword, category, equipment_data)
        except Exception as e:
            logger.error(f"大模型装备整理失败: {e}")
            enriched = {"items": equipment_data, "summary": "数据整理失败"}
    else:
        enriched = {"items": [], "summary": f"未找到与「{keyword}」相关的装备信息"}

    # 4. 缓存
    await _cache_equipment(cache_key, category, enriched, db)

    return enriched


async def recommend_equipment(params: dict, db: AsyncSession) -> dict:
    """
    装备推荐：基于路线参数生成装备方案
    """
    mode = params.get("mode", "light")
    days = params.get("days", 1)
    season = params.get("season", "春")
    terrain = params.get("terrain", "山地")
    people_count = params.get("people_count", 1)

    # 构建 LLM 提示词
    system_prompt = """你是一个专业的户外装备顾问。根据用户提供的徒步参数，生成详细的装备推荐方案。

你需要区分两种模式：
- **重装徒步**：全程自行背负所有装备，无补给点，需要帐篷、睡袋、炊具等全套露营装备
- **轻装徒步**：沿途有住宿/补给点，仅需携带当日所需物品，无需帐篷等过夜装备

请按以下分类输出装备清单：
1. 服装类（含冲锋衣、速干衣、保暖层等）
2. 鞋靴类
3. 背包类
4. 帐篷/睡眠类（仅重装）
5. 炊具/饮食类（重装需要炉具，轻装仅需水具）
6. 登山配件（登山杖、头灯、护膝等）
7. 急救用品

每件装备包含：名称、选购建议、参考价格区间。最后给出轻量化替代方案。"""

    user_message = f"""徒步参数：
- 模式：{"重装徒步（全程背负）" if mode == "heavy" else "轻装徒步（有补给）"}
- 天数：{days}天
- 季节：{season}
- 地形：{terrain}
- 人数：{people_count}人

请生成对应的装备推荐方案。"""

    try:
        llm_result = await llm_chat(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=3072,
        )

        return {
            "mode": mode,
            "days": days,
            "equipment_list": llm_result,
            "buying_advice": "以上装备建议在专业户外店或品牌官方渠道购买，确保正品质量。",
            "price_range": "轻装日徒步装备总预算约 1000-3000 元，重装多日徒步装备总预算约 3000-8000 元。",
            "lightweight_alternatives": "优先选择钛合金材质炊具、充气睡垫等轻量化装备以减轻负重。",
        }
    except Exception as e:
        logger.error(f"装备推荐生成失败: {e}")
        raise


async def _get_cached_equipment(keyword: str, db: AsyncSession) -> dict | None:
    """从缓存获取装备数据"""
    await db.execute(
        delete(EquipmentCache).where(EquipmentCache.expires_at < datetime.now(timezone.utc))
    )
    result = await db.execute(
        select(EquipmentCache)
        .where(EquipmentCache.keyword == keyword)
        .where(EquipmentCache.expires_at > datetime.now(timezone.utc))
    )
    entry = result.scalar_one_or_none()
    return entry.equipment_data if entry else None


async def _cache_equipment(keyword: str, category: str | None, data: dict, db: AsyncSession) -> None:
    """写入装备缓存"""
    try:
        entry = EquipmentCache(
            keyword=keyword,
            category=category,
            equipment_data=data,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=EQUIPMENT_CACHE_TTL_HOURS),
        )
        db.add(entry)
        await db.flush()
    except Exception as e:
        logger.error(f"装备缓存写入失败: {e}")


async def _fetch_equipment_data(keyword: str, category: str | None) -> list[dict]:
    """
    联网搜索装备数据（模拟电商平台公开信息搜索）
    实际场景中需对接具体电商平台，这里作为示例框架
    """
    # 构建搜索 URL（通用搜索引擎/电商平台）
    search_term = f"{keyword} 户外装备 {'分类' + category if category else ''}"
    logger.info(f"装备搜索: {search_term}")

    # 尝试从多个来源获取
    items = []

    # 模拟结构化数据返回（实际项目需替换为真实抓取逻辑）
    sample_items = {
        "帐篷": [
            {"name": "三季帐篷", "brand": "NatureHike", "model": "NH15T002", "weight": "2.1kg", "price": "¥599-899", "scenario": "三季徒步", "water_resistance": "PU3000mm", "rating": "4.5/5"},
            {"name": "超轻单人帐", "brand": "3F UL GEAR", "model": "LANSEN 1", "weight": "1.2kg", "price": "¥499-699", "scenario": "轻量化徒步", "water_resistance": "PU2000mm", "rating": "4.3/5"},
        ],
        "登山配件": [
            {"name": "碳纤维登山杖", "brand": "Black Diamond", "model": "112229", "weight": "480g/对", "price": "¥898-1198", "scenario": "全地形", "water_resistance": "N/A", "rating": "4.8/5"},
            {"name": "LED头灯", "brand": "Petzl", "model": "TIKKA", "weight": "86g", "price": "¥199-259", "scenario": "夜间/应急", "water_resistance": "IPX4", "rating": "4.6/5"},
        ],
    }

    if category and category in sample_items:
        items = sample_items[category]
    else:
        for cat_items in sample_items.values():
            items.extend(cat_items)

    return items


async def _enrich_equipment_data(keyword: str, category: str | None, raw_data: list[dict]) -> dict:
    """使用大模型整理装备数据"""
    system_prompt = """你是户外装备专家。请整理装备搜索数据，输出结构化对比分析和选购建议。"""

    user_message = f"关键词：{keyword}\n分类：{category or '全部'}\n数据：\n{json.dumps(raw_data, ensure_ascii=False)}"

    llm_result = await llm_chat(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=2048,
    )

    return {
        "items": raw_data,
        "summary": llm_result,
    }