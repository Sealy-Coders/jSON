from __future__ import annotations

import io
from typing import Any

import pymupdf as fitz
import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


def preprocess_image(img: Image.Image) -> Image.Image:
    """CPU-friendly preprocessing for Polish OCR."""
    arr = np.array(img.convert("RGB"))
    if cv2 is None:
        gray = img.convert("L")
        return gray.point(lambda x: 0 if x < 160 else 255)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if max(h, w) < 1500:
        scale = 1500 / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 5, 50, 50)
    thr = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    return Image.fromarray(thr)


def tesseract_available() -> bool:
    if pytesseract is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_pil(img: Image.Image, lang: str = "pol") -> str:
    if not tesseract_available():
        raise RuntimeError("Tesseract OCR is not installed or not on PATH")
    processed = preprocess_image(img)
    config = "--oem 1 --psm 6"
    return pytesseract.image_to_string(processed, lang=lang, config=config) or ""


def ocr_page(page: Any, dpi: int = 200, lang: str = "pol") -> str:
    """OCR a PyMuPDF page object."""
    if not tesseract_available():
        raise RuntimeError("Tesseract OCR is not installed or not on PATH")
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return ocr_pil(img, lang=lang)
