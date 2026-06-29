"""
认证相关 Pydantic 数据模型
"""
import re
from pydantic import BaseModel, Field, field_validator


class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    email: str = Field(..., max_length=255, description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError("邮箱格式不正确")
        return v.lower().strip()


class UserLoginRequest(BaseModel):
    """用户登录请求 — 支持用户名或邮箱"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class ForgotPasswordRequest(BaseModel):
    """忘记密码 — 发送重置令牌"""
    email: str = Field(..., max_length=255, description="注册邮箱")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError("邮箱格式不正确")
        return v.lower().strip()


class ResetPasswordRequest(BaseModel):
    """重置密码 — 使用令牌设置新密码"""
    token: str = Field(..., description="重置令牌")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    email: str | None = None
    email_verified: bool = False
    role: str
    avatar_url: str | None = None
    created_at: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """JWT 令牌响应"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse