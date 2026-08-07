"""
应用配置管理模块
统一管理数据库、大模型、MCP服务及应用配置，所有配置项通过环境变量加载
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用全局配置"""
    # 数据库配置
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_user: str = "postgres"
    db_password: str = "123456"
    db_name: str = "outdoor_assistant"

    # 大模型配置
    compatible_api_key: str = ""
    compatible_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    compatible_model: str = "deepseek-v4-flash"

    # 代理配置（用于 Docker 容器访问外网，如 Clash 代理 http://host.docker.internal:7890）
    http_proxy: str = ""
    https_proxy: str = ""
    no_proxy: str = ""

    # MCP 服务配置
    mcp_12306_type: str = "streamable_http"
    mcp_12306_url: str = "http://localhost:8002/mcp"

    # 对象存储配置
    storage_backend: str = "local"  # "local" 或 "minio"
    storage_local_dir: str = "app/static/img"  # 本地存储根目录
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_external_url: str = "http://localhost:9000"  # 浏览器可访问的 URL
    minio_buckets: str = "avatars,uploads"  # 逗号分隔的 bucket 名称

    # Redis 配置（不可用时自动降级到 DB/内存缓存）
    redis_url: str = "redis://localhost:6379/0"

    # 超管账号配置
    super_admin_username: str = "admin"
    super_admin_password: str = "admin123"

    # 应用配置
    app_name: str = "户外徒步助手"
    app_version: str = "1.0.0"
    secret_key: str = "outdoor-buddy-secret-key-change-in-production"
    access_token_expire_minutes: int = 1440
    app_base_url: str = "http://localhost:8001"  # 前端地址，用于邮件中的链接

    # 邮件服务配置（SMTP，可选）
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@outdoorbuddy.com"
    smtp_use_tls: bool = True

    @property
    def minio_bucket_list(self) -> list[str]:
        """解析逗号分隔的 bucket 名称"""
        return [b.strip() for b in self.minio_buckets.split(",") if b.strip()]

    @property
    def database_url(self) -> str:
        """构建异步数据库连接 URL"""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """构建同步数据库连接 URL"""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """获取全局配置单例"""
    return Settings()