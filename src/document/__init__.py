"""文档处理子包: PDF 渲染、图像预处理、页面定位、表格候选检测."""

from src.document.image_preprocessor import preprocess_page
from src.document.page_selector import PageCandidate, select_pages
from src.document.table_detector import detect_tables

__all__ = ["preprocess_page", "select_pages", "PageCandidate", "detect_tables"]
