"""文档加载器: 将 PDF / 图片统一封装为 Document -> Page -> Image 流程.

PDF 通过 PyMuPDF 渲染为页面图像; 图片直接作为单页文档.
"""

from __future__ import annotations

from pathlib import Path

from src.observability.logger import get_logger
from src.table.models import Document, ErrorCode, Page, TableAgentError

logger = get_logger("document_loader")


def is_pdf(file_name: str) -> bool:
    """判断文件是否为 PDF."""
    return file_name.lower().endswith(".pdf")


def is_image(file_name: str) -> bool:
    """判断文件是否为受支持的图片格式."""
    return file_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"))


def load_document(file_path: str | Path, *, dpi: int = 200) -> Document:
    """加载文档, 返回 Document (内部已渲染为页面图像).

    Args:
        file_path: PDF 或图片文件路径.
        dpi: PDF 渲染分辨率.

    Returns:
        Document: 含若干 Page.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise TableAgentError(ErrorCode.FILE_NOT_FOUND, f"document not found: {file_path}")

    name = file_path.name
    if is_pdf(name):
        return _load_pdf(file_path, dpi=dpi)
    if is_image(name):
        return _load_image(file_path)
    raise TableAgentError(ErrorCode.FILE_NOT_FOUND, f"unsupported file type: {name}")


def _load_pdf(file_path: Path, *, dpi: int) -> Document:
    """使用 PyMuPDF 将 PDF 每页渲染为 PNG 图像."""
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover
        raise TableAgentError(ErrorCode.PDF_PARSE_ERROR, "pymupdf not installed") from exc

    try:
        doc = pymupdf.open(str(file_path))
    except Exception as exc:  # noqa: BLE001
        raise TableAgentError(ErrorCode.PDF_PARSE_ERROR, f"failed to open pdf: {exc}") from exc

    pages: list[Page] = []
    out_dir = file_path.parent.parent / "output" / "pages" if file_path.parent.name == "files" else file_path.parent / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        for i, page in enumerate(doc):
            try:
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                img_path = out_dir / f"{file_path.stem}_p{i + 1:03d}.png"
                pix.save(str(img_path))
                pages.append(
                    Page(
                        index=i,
                        image_path=str(img_path),
                        width=pix.width,
                        height=pix.height,
                        rotation_angle=0,
                        text=page.get_text() or "",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("failed to render page %d of %s: %s", i, file_path.name, exc)
    finally:
        doc.close()

    if not pages:
        raise TableAgentError(ErrorCode.PDF_PARSE_ERROR, f"pdf has no renderable pages: {file_path}")

    logger.info("loaded pdf %s: %d pages @ %d dpi", file_path.name, len(pages), dpi)
    return Document(file_name=file_path.name, pages=pages)


def _load_image(file_path: Path) -> Document:
    """将图片视为单页文档."""
    try:
        from PIL import Image

        with Image.open(file_path) as img:
            width, height = img.size
    except Exception as exc:  # noqa: BLE001
        raise TableAgentError(ErrorCode.IMAGE_ERROR, f"failed to open image: {exc}") from exc

    page = Page(index=0, image_path=str(file_path), width=width, height=height, rotation_angle=0)
    logger.info("loaded image %s: %dx%d", file_path.name, width, height)
    return Document(file_name=file_path.name, pages=[page])
