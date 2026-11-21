from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf as fitz

from odwolania2json.normalize import fix_ocr_text


@dataclass
class PageText:
    page_number: int  # 1-based
    text: str
    char_count: int
    used_ocr: bool = False
    method: str = "pdf_text"


@dataclass
class DocumentText:
    path: Path
    pages: list[PageText] = field(default_factory=list)
    max_pages: int = 3

    @property
    def full_text(self) -> str:
        parts = []
        for p in self.pages:
            parts.append(f"\n----- PAGE {p.page_number} -----\n{p.text}")
        return "\n".join(parts).strip()

    @property
    def plain_text(self) -> str:
        return "\n".join(p.text for p in self.pages if p.text).strip()


def extract_pdf_text(
    pdf_path: str | Path,
    max_pages: int = 3,
    min_chars_per_page: int = 80,
    ocr_enabled: bool = True,
    ocr_dpi: int = 200,
    ocr_lang: str = "pol",
) -> DocumentText:
    """Extract text from first max_pages; OCR pages with insufficient text layer."""
    path = Path(pdf_path)
    doc = fitz.open(path)
    result = DocumentText(path=path, max_pages=max_pages)
    n = min(len(doc), max_pages)

    ocr_mod = None
    if ocr_enabled:
        from odwolania2json import ocr as ocr_mod

    for i in range(n):
        page = doc[i]
        raw = page.get_text("text") or ""
        text = fix_ocr_text(raw)
        used_ocr = False
        method = "pdf_text"
        if len(text.strip()) < min_chars_per_page and ocr_enabled and ocr_mod is not None:
            try:
                ocr_text = ocr_mod.ocr_page(page, dpi=ocr_dpi, lang=ocr_lang)
                if len(ocr_text.strip()) > len(text.strip()):
                    text = fix_ocr_text(ocr_text)
                    used_ocr = True
                    method = "tesseract_ocr"
            except Exception:
                # Keep native text if OCR fails (Tesseract missing etc.)
                pass
        result.pages.append(
            PageText(
                page_number=i + 1,
                text=text,
                char_count=len(text.strip()),
                used_ocr=used_ocr,
                method=method,
            )
        )
    doc.close()
    return result


def page_for_span(doc_text: DocumentText, span: str | None) -> int | None:
    if not span:
        return None
    needle = span[:80]
    for p in doc_text.pages:
        if needle in p.text:
            return p.page_number
    return doc_text.pages[0].page_number if doc_text.pages else None
