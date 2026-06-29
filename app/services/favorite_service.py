"""
收藏管理服务模块
支持路线、装备清单、行程预案的收藏与持久化存储
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.favorite import Favorite
from app.utils.logger import logger


async def add_favorite(
    user_id: int,
    fav_type: str,
    title: str,
    content: dict,
    db: AsyncSession,
) -> dict:
    """
    添加收藏
    Args:
        user_id: 用户ID
        fav_type: 收藏类型 (route/equipment/plan)
        title: 收藏标题
        content: 收藏内容
        db: 数据库会话
    Returns:
        创建的收藏信息
    """
    if fav_type not in ("route", "equipment", "plan"):
        raise ValueError(f"不支持的收藏类型: {fav_type}")

    favorite = Favorite(
        user_id=user_id,
        fav_type=fav_type,
        title=title,
        content=content,
    )
    db.add(favorite)
    await db.flush()
    await db.refresh(favorite)

    logger.info(f"收藏已添加: user={user_id}, type={fav_type}, title={title}")

    return {
        "id": favorite.id,
        "fav_type": favorite.fav_type,
        "title": favorite.title,
        "content": favorite.content,
        "created_at": str(favorite.created_at),
    }


async def get_favorites(
    user_id: int,
    fav_type: str | None,
    db: AsyncSession,
) -> list[dict]:
    """
    获取收藏列表
    Args:
        user_id: 用户ID
        fav_type: 收藏类型筛选（可选）
        db: 数据库会话
    """
    query = select(Favorite).where(Favorite.user_id == user_id)
    if fav_type:
        query = query.where(Favorite.fav_type == fav_type)
    query = query.order_by(Favorite.created_at.desc())

    result = await db.execute(query)
    favorites = result.scalars().all()

    return [
        {
            "id": f.id,
            "fav_type": f.fav_type,
            "title": f.title,
            "content": f.content,
            "created_at": str(f.created_at),
        }
        for f in favorites
    ]


async def delete_favorite(favorite_id: int, user_id: int, db: AsyncSession) -> bool:
    """
    删除收藏
    """
    result = await db.execute(
        select(Favorite).where(
            Favorite.id == favorite_id,
            Favorite.user_id == user_id,
        )
    )
    favorite = result.scalar_one_or_none()

    if not favorite:
        return False

    await db.delete(favorite)
    await db.flush()
    logger.info(f"收藏已删除: id={favorite_id}")
    return True


async def export_as_text(content: dict, export_type: str) -> str:
    """
    将装备清单/行程预案导出为纯文本格式
    """
    if export_type == "equipment":
        return _export_equipment_text(content)
    elif export_type == "plan":
        return _export_plan_text(content)
    else:
        return str(content)


def _export_equipment_text(content: dict) -> str:
    """导出装备清单为文本"""
    lines = ["=" * 40, "户外徒步装备清单", "=" * 40, ""]
    if content.get("mode"):
        lines.append(f"模式: {content['mode']}")
    if content.get("days"):
        lines.append(f"天数: {content['days']}天")
    lines.append("")
    if content.get("equipment_list"):
        lines.append("【装备清单】")
        lines.append(str(content["equipment_list"]))
    lines.append("")
    if content.get("buying_advice"):
        lines.append(f"【选购建议】{content['buying_advice']}")
    if content.get("price_range"):
        lines.append(f"【价格区间】{content['price_range']}")
    lines.append("")
    lines.append(f"生成时间: {content.get('created_at', '')}")
    return "\n".join(lines)


def _export_plan_text(content: dict) -> str:
    """导出行程预案为文本"""
    lines = ["=" * 40, "徒步行程智能预案", "=" * 40, ""]
    if content.get("altitude_plan"):
        lines.append("【海拔健康应对方案】")
        lines.append(str(content["altitude_plan"]))
        lines.append("")
    if content.get("fitness_plan"):
        lines.append("【体能与行程分配】")
        lines.append(str(content["fitness_plan"]))
        lines.append("")
    if content.get("weather_risk_plan"):
        lines.append("【天气风险应对】")
        lines.append(str(content["weather_risk_plan"]))
        lines.append("")
    if content.get("environment_knowledge"):
        lines.append("【环境安全知识】")
        lines.append(str(content["environment_knowledge"]))
        lines.append("")
    if content.get("daily_guide"):
        lines.append("【每日行动指南】")
        lines.append(str(content["daily_guide"]))
        lines.append("")
    lines.append(f"生成时间: {content.get('created_at', '')}")
    return "\n".join(lines)