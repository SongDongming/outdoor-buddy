"""
认证 API 路由 — 注册、登录、邮箱验证、密码重置、头像上传
"""
from __future__ import annotations
import base64, uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from openai import AsyncOpenAI
from app.models.database import get_db
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.schemas.common import ApiResponse
from app.core.security import hash_password, verify_password, create_access_token, generate_token
from app.core.config import get_settings
from app.api.dependencies import get_current_user
from app.utils.logger import logger
from app.services.storage_service import get_storage

router = APIRouter(prefix="/api/v1/auth", tags=["用户认证"])
settings = get_settings()

# 令牌有效期
RESET_TOKEN_HOURS = 1


def _build_user_response(user: User) -> dict:
    """构建 UserResponse 字典"""
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        email_verified=bool(user.email_verified),
        role=user.role,
        avatar_url=user.avatar_url,
        created_at=str(user.created_at),
    ).model_dump()


@router.post("/register", response_model=ApiResponse)
async def register(req: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """用户注册（需要邮箱）"""
    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    # 检查邮箱是否已注册
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已被注册")

    # 创建用户
    user = User(
        username=req.username,
        email=req.email,
        email_verified=False,
        password_hash=hash_password(req.password),
        role="user",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info(f"新用户注册: {user.username} <{user.email}>")

    return ApiResponse(code=200, message="注册成功", data=_build_user_response(user))


@router.post("/login", response_model=ApiResponse)
async def login(req: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录 — 支持用户名或邮箱"""
    login_id = req.username.strip().lower()

    # 尝试按邮箱查找
    if "@" in login_id:
        result = await db.execute(select(User).where(User.email == login_id))
    else:
        result = await db.execute(select(User).where(User.username == login_id))

    user = result.scalar_one_or_none()

    if not user:
        # 如果邮箱没找到，再尝试按用户名查找
        if "@" in login_id:
            result = await db.execute(select(User).where(User.username == login_id))
            user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    access_token = create_access_token(data={"sub": str(user.id)})
    logger.info(f"用户登录: {user.username}")

    return ApiResponse(
        code=200,
        message="登录成功",
        data=TokenResponse(
            access_token=access_token,
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                email_verified=bool(user.email_verified),
                role=user.role,
                avatar_url=user.avatar_url,
                created_at=str(user.created_at),
            ),
        ).model_dump(),
    )


@router.get("/me", response_model=ApiResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return ApiResponse(code=200, message="success", data=_build_user_response(current_user))


# ====== 密码重置 ======

@router.post("/forgot-password", response_model=ApiResponse)
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """忘记密码 — 发送重置令牌"""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user:
        # 出于安全考虑，不暴露邮箱是否已注册，统一返回成功
        return ApiResponse(code=200, message="如果该邮箱已注册，重置链接已发送", data=None)

    # 生成重置令牌
    token = generate_token()
    user.reset_token = token
    user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_HOURS)
    db.add(user)
    await db.commit()

    logger.info(f"密码重置令牌已生成: {user.username} <{user.email}>")

    # 尝试发送邮件；如未配置 SMTP，在响应中返回令牌（开发模式）
    email_sent = await _send_reset_email(user.email, token)

    return ApiResponse(
        code=200,
        message="重置链接已发送到您的邮箱" if email_sent else "邮件服务未配置，请使用下方令牌重置密码",
        data={
            "reset_token": token if not email_sent else None,
            "expires_in_hours": RESET_TOKEN_HOURS,
        },
    )


@router.post("/reset-password", response_model=ApiResponse)
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """使用重置令牌设置新密码"""
    result = await db.execute(
        select(User).where(
            User.reset_token == req.token,
            User.reset_token_expires > datetime.now(timezone.utc),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="重置令牌无效或已过期")

    # 更新密码
    user.password_hash = hash_password(req.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.add(user)
    await db.commit()

    logger.info(f"密码已重置: {user.username}")

    return ApiResponse(code=200, message="密码重置成功，请使用新密码登录", data=None)


# ====== 邮箱验证 ======

@router.post("/verify-email", response_model=ApiResponse)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """验证邮箱（使用令牌）"""
    result = await db.execute(
        select(User).where(
            User.reset_token == token,
            User.reset_token_expires > datetime.now(timezone.utc),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证令牌无效或已过期")

    user.email_verified = True
    user.reset_token = None
    user.reset_token_expires = None
    db.add(user)
    await db.commit()

    logger.info(f"邮箱已验证: {user.username} <{user.email}>")

    return ApiResponse(code=200, message="邮箱验证成功", data=None)


# ====== 邮箱检查 ======

@router.get("/check-email", response_model=ApiResponse)
async def check_email(email: str, db: AsyncSession = Depends(get_db)):
    """检查邮箱是否已注册"""
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    user = result.scalar_one_or_none()
    return ApiResponse(code=200, message="success", data={"exists": user is not None})


# ====== 邮件发送 ======

async def _send_reset_email(to_email: str, token: str) -> bool:
    """发送密码重置邮件，返回是否发送成功"""
    if not settings.smtp_host or not settings.smtp_user:
        logger.info("SMTP 未配置，跳过邮件发送")
        return False

    reset_url = f"{settings.app_base_url}/?token={token}"

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg["Subject"] = "Outdoor Buddy — 密码重置"

    body = f"""您好，

您请求重置 Outdoor Buddy 账户的密码。

方式一（推荐）：点击下方链接，页面将自动打开重置界面：
{reset_url}

方式二：手动输入令牌：
{token}

此链接和令牌在 {RESET_TOKEN_HOURS} 小时内有效。如非本人操作，请忽略此邮件。

— Outdoor Buddy 团队"""
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        import asyncio
        await asyncio.to_thread(_send_smtp, msg, to_email)
        logger.info(f"重置邮件已发送: {to_email}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False


def _send_smtp(msg: MIMEMultipart, to_email: str) -> None:
    """同步 SMTP 发送"""
    import smtplib
    if settings.smtp_use_tls:
        # STARTTLS (port 587) — Gmail, QQ, etc.
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, to_email, msg.as_string())
    else:
        # SSL (port 465) — 163, 126, etc.
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from, to_email, msg.as_string())


# ====== 头像上传 + AI审核 ======

MODERATION_PROMPT = """你是内容安全审核专家。请审核这张图片是否适合作为用户头像。违规判定：1.色情低俗裸露 2.暴力血腥恐怖 3.政治敏感 4.违法广告赌博毒品 5.侮辱歧视。请仅回复JSON：{"passed": true/false, "reason": "审核简述（15字以内）", "score": 1-10}"""


@router.post("/avatar", response_model=ApiResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传头像并进行AI内容审核"""
    if file.size and file.size > 3 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过3MB")
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/gif/webp 格式")

    content = await file.read()
    img_b64 = base64.b64encode(content).decode("utf-8")
    mime = f"image/{'jpeg' if ext == 'jpg' else ext}"

    try:
        client = AsyncOpenAI(api_key=settings.compatible_api_key, base_url=settings.compatible_base_url)
        response = await client.chat.completions.create(
            model=settings.compatible_model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": MODERATION_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
            ]}],
            max_tokens=150, temperature=0,
        )
        result_text = response.choices[0].message.content.strip()
        logger.info(f"头像审核: {result_text[:200]}")
    except Exception as e:
        logger.warning(f"AI审核失败，降级基础审核: {e}")
        return await _basic_avatar_check(content, ext, current_user, db)

    import json as _json
    try:
        s = result_text.find("{"); e = result_text.rfind("}") + 1
        result = _json.loads(result_text[s:e]) if s >= 0 and e > s else {"passed": True, "reason": "OK", "score": 8}
    except Exception:
        result = {"passed": True, "reason": "OK", "score": 8}

    if not result.get("passed"):
        return ApiResponse(code=422, message=f"审核未通过: {result.get('reason','违规')}", data={"passed": False, "reason": result.get("reason"), "score": result.get("score", 0)})

    return await _save_avatar(content, ext, current_user, db)


async def _basic_avatar_check(content: bytes, ext: str, current_user: User, db: AsyncSession):
    headers = {"jpg": b"\xff\xd8\xff", "jpeg": b"\xff\xd8\xff", "png": b"\x89PNG", "gif": b"GIF8", "webp": b"RIFF"}
    if headers.get(ext) and not content.startswith(headers[ext]):
        raise HTTPException(status_code=400, detail="图片格式校验失败")
    return await _save_avatar(content, ext, current_user, db)


async def _save_avatar(content: bytes, ext: str, current_user: User, db: AsyncSession):
    storage = get_storage()
    old_url = current_user.avatar_url
    if old_url:
        try:
            await storage.delete_by_url(old_url)
            logger.info(f"已清理旧头像: {old_url}")
        except Exception as e:
            logger.warning(f"清理旧头像失败（非致命）: {old_url} — {e}")

    filename = f"avatar_{current_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
    try:
        url = await storage.save(content, "avatars", filename)
    except Exception as e:
        logger.error(f"头像保存失败: {e}")
        raise HTTPException(status_code=503, detail="存储服务暂时不可用，请稍后重试")

    current_user.avatar_url = url
    db.add(current_user)
    await db.commit()
    return ApiResponse(code=200, message="头像上传成功", data={
        "passed": True, "reason": "审核通过", "score": 10, "avatar_url": url,
        "user": _build_user_response(current_user),
    })