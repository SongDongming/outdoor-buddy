"""
收藏管理 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.user import User
from app.api.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.services.favorite_service import (
    add_favorite,
    get_favorites,
    delete_favorite,
    export_as_text,
)
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/favorites", tags=["收藏管理"])


@router.post("/add", response_model=ApiResponse)
async def add_favorite_api(
    request: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """添加收藏：路线、装备清单或行程预案"""
    fav_type = request.get("fav_type", "")
    title = request.get("title", "")
    content = request.get("content", {})

    if fav_type not in ("route", "equipment", "plan"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="收藏类型必须为 route、equipment 或 plan",
        )

    try:
        result = await add_favorite(current_user.id, fav_type, title, content, db)
    except Exception as e:
        logger.error(f"添加收藏失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="收藏添加失败",
        )

    return ApiResponse(code=200, message="收藏成功", data=result)


@router.get("/list", response_model=ApiResponse)
async def list_favorites_api(
    fav_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取收藏列表，可按类型筛选"""
    try:
        favorites = await get_favorites(current_user.id, fav_type, db)
    except Exception as e:
        logger.error(f"获取收藏列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取收藏列表失败",
        )

    return ApiResponse(
        code=200,
        message="success",
        data={"favorites": favorites, "total": len(favorites)},
    )


@router.delete("/{favorite_id}", response_model=ApiResponse)
async def delete_favorite_api(
    favorite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除收藏"""
    success = await delete_favorite(favorite_id, current_user.id, db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="收藏不存在或无权操作",
        )

    return ApiResponse(code=200, message="已取消收藏", data=None)


@router.post("/export/{export_type}", response_model=ApiResponse)
async def export_favorite_api(
    export_type: str,
    request: dict,
    current_user: User = Depends(get_current_user),
):
    """
    导出装备清单/行程预案为纯文本
    export_type: equipment 或 plan
    """
    if export_type not in ("equipment", "plan"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="导出类型必须为 equipment 或 plan",
        )

    content = request.get("content", {})
    text = await export_as_text(content, export_type)

    return ApiResponse(code=200, message="success", data={"text": text})