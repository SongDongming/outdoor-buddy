"""
通用响应模型
"""
from typing import Any, Optional
from pydantic import BaseModel


class ApiResponse(BaseModel):
    """统一 API 响应格式"""
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None


class PaginatedResponse(BaseModel):
    """分页响应"""
    code: int = 200
    message: str = "success"
    data: list = []
    total: int = 0
    page: int = 1
    page_size: int = 20