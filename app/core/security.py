"""
安全模块 — 密码哈希与 JWT 令牌管理
使用 hashlib pbkdf2_hmac 实现密码哈希，避免 passlib/bcrypt 版本兼容问题
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.core.config import get_settings

settings = get_settings()

# JWT 算法
ALGORITHM = "HS256"
# PBKDF2 参数
HASH_ITERATIONS = 100000
SALT_LENGTH = 32


def hash_password(password: str) -> str:
    """对明文密码进行 PBKDF2-SHA256 哈希，返回格式: iterations$salt$hash"""
    salt = secrets.token_hex(SALT_LENGTH)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), HASH_ITERATIONS)
    return f"{HASH_ITERATIONS}${salt}${dk.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希值是否匹配"""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        iterations = int(parts[0])
        salt = parts[1]
        stored_hash = parts[2]
        dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt.encode(), iterations)
        return secrets.compare_digest(dk.hex(), stored_hash)
    except (ValueError, IndexError, AttributeError):
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT 访问令牌"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT 访问令牌，验证失败返回 None"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def generate_token(length: int = 32) -> str:
    """生成 URL-safe 随机令牌（用于密码重置、邮箱验证）"""
    return secrets.token_urlsafe(length)