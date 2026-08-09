"""
导出 API — 海报 PDF 生成
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app.models.user import User
from app.api.dependencies import get_current_user
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/export", tags=["导出"])


class PdfExportRequest(BaseModel):
    html: str = Field(..., description="完整海报 HTML 文档")
    title: str = Field("export", max_length=200, description="下载文件名标题")


@router.post("/pdf")
async def export_pdf(req: PdfExportRequest, current_user: User = Depends(get_current_user)):
    """把海报 HTML 渲染为 PDF 并返回（weasyprint，支持中文）；需登录"""
    from app.services.pdf_service import generate_pdf
    try:
        pdf = await asyncio.to_thread(generate_pdf, req.html)
    except Exception as e:
        logger.error(f"[PDF] 导出失败: {e}")
        raise HTTPException(status_code=500, detail="PDF 生成失败，请稍后重试")

    filename = f"{req.title}.pdf"
    # RFC 5987 编码文件名（中文文件名）
    from urllib.parse import quote
    disposition = f"attachment; filename=\"export.pdf\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )
