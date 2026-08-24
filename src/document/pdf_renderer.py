"""PDF 渲染工具.

PyMuPDF 已在 io/document_loader 中直接使用, 这里仅提供可独立调用的辅助函数
(例如按页码范围渲染).
"""

from __future__ import annotations

from pathlib import Path

from src.observability.logger import get_logger
from src.table.models import ErrorCode, TableAgentError

logger = get_logger("pdf_renderer")


def render_pdf_pages(pdf_path: str | Path, out_dir: str | Path, *, dpi: int = 200, page_indices: list[int] | None = None) -> list[str]:
    """渲染 PDF 为页面 PNG 图像.

    Args:
        pdf_path: PDF 路径.
        out_dir: 输出目录.
        dpi: 渲染分辨率.
        page_indices: 指定页码 (0-based) 列表, None 表示全部.

    Returns:
        渲染后的图像路径列表.
    """
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover
        raise TableAgentError(ErrorCode.PDF_PARSE_ERROR, "pymupdf not installed") from exc

    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as exc:  # noqa: BLE001
        raise TableAgentError(ErrorCode.PDF_PARSE_ERROR, f"failed to open pdf: {exc}") from exc

    paths: list[str] = []
    try:
        total = doc.page_count
        idx_list = page_indices if page_indices is not None else list(range(total))
        for i in idx_list:
            if i < 0 or i >= total:
                continue
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            out_path = out_dir / f"{pdf_path.stem}_p{i + 1:03d}.png"
            pix.save(str(out_path))
            paths.append(str(out_path))
    finally:
        doc.close()

    logger.info("rendered %d/%d pages from %s", len(paths), doc.page_count if 'doc' in dir() else -1, pdf_path.name)
    return paths
