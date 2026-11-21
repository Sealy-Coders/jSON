from __future__ import annotations

import io
import platform
import shutil
from functools import lru_cache
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


class OcrUnavailable(RuntimeError):
    """Raised when OCR is requested but Tesseract (or the language pack) is missing."""


def install_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        return "brew install tesseract tesseract-lang"
    if system == "Windows":
        return "zainstaluj Tesseract z https://github.com/UB-Mannheim/tesseract/wiki (zaznacz język Polish) i dodaj do PATH"
    return "sudo apt install tesseract-ocr tesseract-ocr-pol"


@lru_cache(maxsize=1)
def ocr_status(lang: str = "pol") -> dict[str, Any]:
    """Detect Tesseract and language packs once per process; never raises."""
    status: dict[str, Any] = {
        "available": False,
        "version": None,
        "languages": [],
        "requested_lang": lang,
        "lang_available": False,
        "effective_lang": None,
        "message": "",
        "hint": install_hint(),
    }
    if pytesseract is None:
        status["message"] = "Brak pakietu pytesseract (pip install pytesseract)."
        return status
    if shutil.which("tesseract") is None and not getattr(pytesseract.pytesseract, "tesseract_cmd", "").startswith("/"):
        status["message"] = "Tesseract nie jest zainstalowany — skany bez warstwy tekstowej nie zostaną odczytane."
        return status
    try:
        status["version"] = str(pytesseract.get_tesseract_version())
        status["languages"] = sorted(pytesseract.get_languages(config=""))
    except Exception as exc:  # noqa: BLE001
        status["message"] = f"Tesseract nie odpowiada: {exc}"
        return status
    status["available"] = True
    if lang in status["languages"]:
        status["lang_available"] = True
        status["effective_lang"] = lang
        status["message"] = f"OCR gotowy (Tesseract {status['version']}, język {lang})."
    elif "eng" in status["languages"]:
        status["effective_lang"] = "eng"
        status["message"] = (
            f"Brak języka '{lang}' — OCR działa w trybie 'eng' (gorsze polskie znaki, "
            "część naprawia słownik OCR)."
        )
    else:
        status["available"] = False
        status["message"] = f"Tesseract bez języka '{lang}' ani 'eng'."
    return status


def tesseract_available() -> bool:
    return bool(ocr_status()["available"])


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


def ocr_pil(img: Image.Image, lang: str = "pol") -> str:
    status = ocr_status(lang)
    if not status["available"]:
        raise OcrUnavailable(f"{status['message']} Instalacja: {status['hint']}")
    processed = preprocess_image(img)
    primary = pytesseract.image_to_string(processed, lang=status["effective_lang"], config="--oem 1 --psm 6") or ""
    fallback = pytesseract.image_to_string(processed, lang=status["effective_lang"], config="--oem 1 --psm 3") or ""
    return fallback if len(fallback.strip()) > len(primary.strip()) else primary


def ocr_page(page: Any, dpi: int = 200, lang: str = "pol") -> str:
    """OCR a PyMuPDF page object."""
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return ocr_pil(img, lang=lang)


def page_fallback_text(page: Any) -> str:
    """Text that exists without OCR: annotations, form fields, link targets.

    Used for image-only pages when Tesseract is unavailable — better than nothing,
    and never invents content.
    """
    parts: list[str] = []
    try:
        for annot in page.annots() or []:
            content = (annot.info or {}).get("content") or ""
            if content.strip():
                parts.append(content.strip())
    except Exception:  # noqa: BLE001
        pass
    try:
        for w in page.widgets() or []:
            name = (w.field_label or w.field_name or "").strip()
            value = str(w.field_value or "").strip()
            if value:
                parts.append(f"{name}: {value}" if name else value)
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(parts)
