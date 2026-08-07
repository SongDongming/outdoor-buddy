"""
超管用户服务模块
应用启动时确保超管账号存在，用于论坛内容管理等后台操作
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.core.security import hash_password
from app.core.config import get_settings
from app.utils.logger import logger


async def ensure_admin_user(db: AsyncSession) -> bool:
    """
    确保超管账号存在，不存在则创建（幂等）
    用户名/密码通过环境变量 SUPER_ADMIN_USERNAME / SUPER_ADMIN_PASSWORD 配置
    """
    settings = get_settings()
    result = await db.execute(select(User).where(User.username == settings.super_admin_username))
    user = result.scalar_one_or_none()

    if user:
        if user.role != "admin":
            user.role = "admin"
            await db.commit()
            logger.info(f"已将 {user.username} 提升为管理员")
        return False

    admin = User(
        username=settings.super_admin_username,
        email=None,
        email_verified=True,
        password_hash=hash_password(settings.super_admin_password),
        role="admin",
    )
    db.add(admin)
    await db.commit()
    logger.info(f"超管账号已创建: {admin.username} (role=admin)")
    return True
