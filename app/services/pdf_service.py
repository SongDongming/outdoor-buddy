"""
PDF 导出服务 — weasyprint 将海报 HTML 渲染为 PDF（支持中文）
用于行程预案 / 装备方案的 PDF 下载。weasyprint 依赖系统 pango 与中文字体（见 Dockerfile）。
"""
from app.utils.logger import logger


def generate_pdf(html: str) -> bytes:
    """把完整 HTML 文档渲染为 PDF 字节（同步阻塞，调用方应放线程池）"""
    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except Exception as e:
        logger.error(f"[PDF] weasyprint 渲染失败: {e}")
        raise
