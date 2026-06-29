"""
对象存储抽象层
支持本地文件系统（开发）和 MinIO S3 兼容存储（容器化部署）
"""
import os
import re
import asyncio
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import get_settings
from app.utils.logger import logger


# ==============================
# 异常定义
# ==============================

class StorageError(Exception):
    """存储操作异常"""


# ==============================
# 抽象基类
# ==============================

class StorageBackend(ABC):
    """存储后端抽象基类"""

    @abstractmethod
    async def save(self, data: bytes, bucket: str, filename: str) -> str:
        """保存文件，返回公开访问 URL（异步）"""

    @abstractmethod
    async def delete(self, bucket: str, filename: str) -> bool:
        """删除文件，返回是否成功（异步）"""

    async def delete_by_url(self, url: str) -> bool:
        """根据公开 URL 解析并删除文件"""
        bucket, filename = self._parse_url(url)
        if bucket and filename:
            return await self.delete(bucket, filename)
        return False

    @abstractmethod
    async def get_url(self, bucket: str, filename: str) -> str:
        """构造公开访问 URL"""

    @abstractmethod
    def _parse_url(self, url: str) -> tuple[str | None, str | None]:
        """从公开 URL 中提取 bucket 和 filename"""

    # ---- 同步方法（供迁移脚本等同步场景使用）----

    def save_sync(self, data: bytes, bucket: str, filename: str) -> str:
        """保存文件（同步版本），返回公开访问 URL"""
        raise NotImplementedError

    def delete_sync(self, bucket: str, filename: str) -> bool:
        """删除文件（同步版本），返回是否成功"""
        raise NotImplementedError


# ==============================
# 本地文件系统后端
# ==============================

class LocalStorageBackend(StorageBackend):
    """本地磁盘存储（开发环境默认）"""

    def __init__(self, base_dir: str = "app/static/img"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        # derive URL prefix from base_dir relative to app/static
        base_norm = os.path.normpath(self.base_dir)
        if "app" + os.sep + "static" in base_norm:
            # base_dir is under app/static → URL is /static/...
            static_idx = base_norm.index(os.path.join("app", "static"))
            self._url_prefix = "/static" + base_norm[static_idx + len(os.path.join("app", "static")):].replace(os.sep, "/")
        else:
            # base_dir is outside app/static → use /static/img fallback
            self._url_prefix = "/static/img"

    async def save(self, data: bytes, bucket: str, filename: str) -> str:
        bucket_dir = os.path.join(self.base_dir, bucket)
        os.makedirs(bucket_dir, exist_ok=True)
        filepath = os.path.join(bucket_dir, filename)
        await asyncio.to_thread(self._write_file, filepath, data)
        logger.debug(f"[LocalStorage] 已保存: {bucket}/{filename}")
        return f"{self._url_prefix}/{bucket}/{filename}"

    @staticmethod
    def _write_file(filepath: str, data: bytes) -> None:
        with open(filepath, "wb") as f:
            f.write(data)

    async def delete(self, bucket: str, filename: str) -> bool:
        filepath = os.path.join(self.base_dir, bucket, filename)
        try:
            exists = await asyncio.to_thread(os.path.isfile, filepath)
            if not exists:
                logger.debug(f"[LocalStorage] 文件不存在，跳过删除: {bucket}/{filename}")
                return False
            await asyncio.to_thread(os.remove, filepath)
            logger.debug(f"[LocalStorage] 已删除: {bucket}/{filename}")
            return True
        except Exception as e:
            logger.warning(f"[LocalStorage] 删除失败: {bucket}/{filename} — {e}")
            return False

    async def get_url(self, bucket: str, filename: str) -> str:
        return f"{self._url_prefix}/{bucket}/{filename}"

    def _parse_url(self, url: str) -> tuple[str | None, str | None]:
        if not url:
            return None, None
        # match /static/.../bucket/filename pattern
        import re
        pattern = re.compile(re.escape(self._url_prefix) + r"/([^/]+)/(.+)")
        match = pattern.search(url)
        if match:
            return match.group(1), match.group(2)
        return None, None

    def save_sync(self, data: bytes, bucket: str, filename: str) -> str:
        bucket_dir = os.path.join(self.base_dir, bucket)
        os.makedirs(bucket_dir, exist_ok=True)
        filepath = os.path.join(bucket_dir, filename)
        with open(filepath, "wb") as f:
            f.write(data)
        return f"{self._url_prefix}/{bucket}/{filename}"

    def delete_sync(self, bucket: str, filename: str) -> bool:
        filepath = os.path.join(self.base_dir, bucket, filename)
        try:
            if not os.path.isfile(filepath):
                return False
            os.remove(filepath)
            return True
        except Exception as e:
            logger.warning(f"[LocalStorage] 同步删除失败: {bucket}/{filename} — {e}")
            return False


# ==============================
# MinIO S3 兼容后端
# ==============================

_MINIO_POLICY_TEMPLATE = """{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": ["*"]},
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::{bucket}/*"]
    }
  ]
}"""


class MinioStorageBackend(StorageBackend):
    """MinIO 对象存储（容器化部署推荐）"""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        buckets: list[str],
        secure: bool = False,
        external_url: str = "http://localhost:9000",
    ):
        self.endpoint = endpoint
        self.external_url = external_url.rstrip("/")
        self.buckets = buckets

        # 延迟导入以避免本地开发时必须安装 minio
        from minio import Minio

        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        # 同步初始化 bucket（在事件循环启动前完成）
        self._ensure_buckets()

    def _ensure_buckets(self) -> None:
        """确保所有 bucket 存在且设为公开读取"""
        from minio.error import S3Error

        for bucket in self.buckets:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    logger.info(f"[MinIO] Bucket 已创建: {bucket}")
                # 设置公开读取策略
                policy = _MINIO_POLICY_TEMPLATE.replace("{bucket}", bucket)
                self.client.set_bucket_policy(bucket, policy)
                logger.info(f"[MinIO] Bucket 策略已设为 public-read: {bucket}")
            except S3Error as e:
                logger.error(f"[MinIO] Bucket 初始化失败: {bucket} — {e}")

    async def save(self, data: bytes, bucket: str, filename: str) -> str:
        from minio.error import S3Error
        from io import BytesIO

        try:
            await asyncio.to_thread(
                self.client.put_object,
                bucket,
                filename,
                BytesIO(data),
                len(data),
            )
            url = f"{self.external_url}/{bucket}/{filename}"
            logger.debug(f"[MinIO] 已保存: {bucket}/{filename}")
            return url
        except S3Error as e:
            logger.error(f"[MinIO] 保存失败: {bucket}/{filename} — {e}")
            raise StorageError(f"MinIO 保存失败: {e}") from e

    async def delete(self, bucket: str, filename: str) -> bool:
        from minio.error import S3Error

        try:
            await asyncio.to_thread(
                self.client.remove_object, bucket, filename
            )
            logger.debug(f"[MinIO] 已删除: {bucket}/{filename}")
            return True
        except S3Error as e:
            # NoSuchKey 等视为正常 — 幂等删除
            logger.warning(f"[MinIO] 删除失败（可能不存在）: {bucket}/{filename} — {e}")
            return False

    async def get_url(self, bucket: str, filename: str) -> str:
        return f"{self.external_url}/{bucket}/{filename}"

    def _parse_url(self, url: str) -> tuple[str | None, str | None]:
        if not url:
            return None, None
        # URL 格式: {external_url}/{bucket}/{filename}
        # 例如: http://localhost:9000/avatars/avatar_4_6200f19c.png
        prefix = self.external_url + "/"
        if not url.startswith(prefix):
            return None, None
        rest = url[len(prefix):]
        parts = rest.split("/", 1)
        if len(parts) == 2 and parts[0] in self.buckets:
            return parts[0], parts[1]
        return None, None

    def save_sync(self, data: bytes, bucket: str, filename: str) -> str:
        from io import BytesIO

        self.client.put_object(bucket, filename, BytesIO(data), len(data))
        return f"{self.external_url}/{bucket}/{filename}"

    def delete_sync(self, bucket: str, filename: str) -> bool:
        from minio.error import S3Error

        try:
            self.client.remove_object(bucket, filename)
            return True
        except S3Error as e:
            logger.warning(f"[MinIO] 同步删除失败（可能不存在）: {bucket}/{filename} — {e}")
            return False


# ==============================
# 工厂函数
# ==============================

@lru_cache()
def get_storage() -> StorageBackend:
    """获取存储后端单例（根据配置自动选择）"""
    settings = get_settings()

    if settings.storage_backend == "minio":
        logger.info("[Storage] 使用 MinIO 对象存储")
        return MinioStorageBackend(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            external_url=settings.minio_external_url,
            buckets=settings.minio_bucket_list,
        )

    logger.info("[Storage] 使用本地文件存储")
    return LocalStorageBackend(base_dir=settings.storage_local_dir)
