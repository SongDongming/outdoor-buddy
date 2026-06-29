"""
行程智能预案服务模块
自动整合路线、天气、用户参数，生成定制化出行预案与专业知识推送
"""
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.trip_plan import TripPlan
from app.utils.llm_client import llm_chat
from app.utils.logger import logger


async def generate_trip_plan(
    route_params: dict,
    weather_data: dict | None,
    user_params: dict | None,
    user_id: int | None,
    db: AsyncSession,
) -> dict:
    """
    生成行程智能预案
    整合五大核心参数，输出定制化预案
    """
    # 1. 提取核心参数
    days = route_params.get("days", 1)
    max_altitude = route_params.get("max_altitude", 0)
    elevation_gain = route_params.get("elevation_gain", 0)
    difficulty = route_params.get("difficulty", "中等")
    terrain = route_params.get("terrain", "山地")

    # 2. 生成各维度预案
    altitude_plan = await _generate_altitude_plan(max_altitude, days, user_params)
    fitness_plan = await _generate_fitness_plan(days, elevation_gain, difficulty)
    weather_risk_plan = await _generate_weather_risk_plan(weather_data)
    environment_knowledge = await _generate_environment_knowledge(terrain)
    daily_guide = await _generate_daily_guide(days, route_params, weather_data)

    plan_content = {
        "altitude_plan": altitude_plan,
        "fitness_plan": fitness_plan,
        "weather_risk_plan": weather_risk_plan,
        "environment_knowledge": environment_knowledge,
        "daily_guide": daily_guide,
    }

    # 3. 持久化存储
    try:
        trip_plan = TripPlan(
            user_id=user_id,
            route_params=route_params,
            weather_data=weather_data,
            plan_content=plan_content,
        )
        db.add(trip_plan)
        await db.flush()
        plan_content["plan_id"] = trip_plan.id
        logger.info(f"行程预案已保存: id={trip_plan.id}")
    except Exception as e:
        logger.error(f"行程预案保存失败: {e}")

    return plan_content


async def regenerate_plan(
    plan_id: int,
    route_params: dict | None,
    weather_data: dict | None,
    user_params: dict | None,
    db: AsyncSession,
) -> dict:
    """
    根据更新后的参数重新生成预案
    """
    # 获取已有预案
    existing = await db.execute(select(TripPlan).where(TripPlan.id == plan_id))
    plan = existing.scalar_one_or_none()

    if not plan:
        raise ValueError(f"预案不存在: {plan_id}")

    # 合并参数
    merged_route = {**(plan.route_params or {}), **(route_params or {})}
    merged_weather = {**(plan.weather_data or {}), **(weather_data or {})}

    # 重新生成
    return await generate_trip_plan(
        route_params=merged_route,
        weather_data=merged_weather,
        user_params=user_params,
        user_id=plan.user_id,
        db=db,
    )


async def _generate_altitude_plan(max_altitude: int, days: int, user_params: dict | None) -> str:
    """生成海拔健康应对方案"""
    system_prompt = """你是高海拔户外医学专家。根据海拔高度分级评估高反风险：

- 低于3000米：低风险，基础建议
- 3000-4000米：中风险，详细应对方案
- 4000米以上：高风险，强化安全提示与禁忌事项

输出内容：海拔适应节奏建议、高反症状识别与处置方法、必备药品清单。"""

    altitude_level = "低风险" if max_altitude < 3000 else ("中风险" if max_altitude < 4000 else "高风险")
    user_info = json.dumps(user_params, ensure_ascii=False) if user_params else "未提供"

    user_message = f"最高海拔：{max_altitude}米（{altitude_level}），徒步天数：{days}天，用户信息：{user_info}"

    try:
        return await llm_chat(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2048,
        )
    except Exception as e:
        logger.error(f"海拔方案生成失败: {e}")
        return f"海拔 {max_altitude}米，{altitude_level}。请做好适应性准备，携带常用药品。"


async def _generate_fitness_plan(days: int, elevation_gain: int, difficulty: str) -> str:
    """生成体能与行程分配建议"""
    system_prompt = """你是户外体能训练专家。根据徒步参数拆分每日行程强度，给出：
- 休息节点规划
- 补水补能节奏
- 爬坡/下坡发力技巧
- 单日行走时长建议"""

    user_message = f"徒步天数：{days}天，累计爬升：{elevation_gain}米，难度：{difficulty}"

    try:
        return await llm_chat(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2048,
        )
    except Exception as e:
        logger.error(f"体能方案生成失败: {e}")
        return f"{days}天行程，累计爬升{elevation_gain}米。建议合理分配体力，每2小时休息一次。"


async def _generate_weather_risk_plan(weather_data: dict | None) -> str:
    """生成天气风险应对预案"""
    if not weather_data:
        return "暂无天气数据，建议出行前查询实时天气。"

    system_prompt = """你是户外天气风险专家。匹配预报天气情况，输出：
- 装备调整建议
- 行程备选方案
- 避险处置要点（雷雨避雷、高温防暑、低温防冻等）"""

    user_message = f"天气数据：\n{json.dumps(weather_data, ensure_ascii=False)}"

    try:
        return await llm_chat(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2048,
        )
    except Exception as e:
        logger.error(f"天气风险预案生成失败: {e}")
        return "请关注当地天气预警，做好相应防护准备。"


async def _generate_environment_knowledge(terrain: str) -> str:
    """生成环境安全知识推送"""
    system_prompt = f"""你是户外安全专家。根据\"{terrain}\"地形特征，推送针对性安全知识：
- 迷路应对方法
- 野生动物防范
- 水源安全
- LNT环保准则
- 应急求救方法"""

    user_message = f"地形类型：{terrain}"

    try:
        return await llm_chat(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2048,
        )
    except Exception as e:
        logger.error(f"环境知识生成失败: {e}")
        return f"在{terrain}地形徒步时，请注意安全，遵守LNT环保准则。"


async def _generate_daily_guide(days: int, route_params: dict, weather_data: dict | None) -> str:
    """生成逐日行动指南"""
    system_prompt = """你是户外徒步领队。按天生成每日行动指南，包含：
- 当日准备事项
- 时间规划建议
- 重点注意事项"""

    user_message = f"徒步天数：{days}天\n路线参数：{json.dumps(route_params, ensure_ascii=False)}\n天气：{json.dumps(weather_data, ensure_ascii=False) if weather_data else '无'}"

    try:
        return await llm_chat(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=3072,
        )
    except Exception as e:
        logger.error(f"每日指南生成失败: {e}")
        return f"共{days}天行程，请根据实际路况和天气灵活调整每日计划。"