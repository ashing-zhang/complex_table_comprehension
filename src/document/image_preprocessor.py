"""图像预处理 (TECHNICAL_SOLUTION.md 第 7.2 章).

支持 resize / grayscale / 对比度增强 / 去噪 / 纠偏 / 裁剪.
关键约束: 预处理不覆盖原图, 保留 original + processed 两份.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.observability.logger import get_logger
from src.table.models import ErrorCode, Page, TableAgentError

logger = get_logger("image_preprocessor")


def _ensure_long_side(img: np.ndarray, max_long_side: int) -> np.ndarray:
    """按最长边限制 resize, 避免超过模型输入上限."""
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_long_side:
        return img
    scale = max_long_side / longest
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """简单纠偏: 基于 minAreaRect 估计文本倾斜角度."""
    try:
        thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thr > 0))
        if coords.shape[0] < 50:
            return gray, 0.0
        angle = float(cv2.minAreaRect(coords)[-1])
        if angle < -45:
            angle = 90 + angle
        if abs(angle) < 0.5:
            return gray, 0.0
        (h, w) = gray.shape
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rotated = cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return rotated, angle
    except Exception as exc:  # noqa: BLE001
        logger.debug("deskew skipped: %s", exc)
        return gray, 0.0


def preprocess_page(page: Page, out_dir: str | Path, *, max_long_side: int = 4096) -> Page:
    """对单页图像执行预处理并写出 processed 图像.

    Args:
        page: 原始页面 (含 original image_path).
        out_dir: 预处理图像输出目录.
        max_long_side: 最长边像素上限.

    Returns:
        更新后的 Page (processed_image_path 已设置).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    src = Path(page.image_path)
    if not src.exists():
        raise TableAgentError(ErrorCode.IMAGE_ERROR, f"page image not found: {src}")

    try:
        img = cv2.imdecode(np.fromfile(str(src), dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            img = cv2.imread(str(src))
    except Exception as exc:  # noqa: BLE001
        raise TableAgentError(ErrorCode.IMAGE_ERROR, f"failed to read image {src}: {exc}") from exc

    if img is None:
        raise TableAgentError(ErrorCode.IMAGE_ERROR, f"failed to decode image: {src}")

    # resize 限制
    img = _ensure_long_side(img, max_long_side)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # 对比度增强 (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    # 去噪
    denoised = cv2.fastNlMeansDenoising(enhanced, None, h=7, templateWindowSize=7, searchWindowSize=21)
    # 纠偏
    deskewed, angle = _deskew(denoised)

    out_path = out_dir / f"{src.stem}_proc.png"
    ok = cv2.imencode(".png", deskewed)[1].tofile(str(out_path))
    if not ok:
        raise TableAgentError(ErrorCode.IMAGE_ERROR, f"failed to write processed image: {out_path}")

    page.processed_image_path = str(out_path)
    if angle:
        page.rotation_angle = round(angle, 2)
    logger.info("preprocessed page %d -> %s (angle=%.2f)", page.index, out_path.name, angle)
    return page
