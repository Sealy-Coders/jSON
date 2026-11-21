from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf as fitz

from odwolania2json.normalize import clean_ocr_page, fix_ocr_text


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
    warnings: list[dict[str, Any]] = field(default_factory=list)

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
    ocr_cleanup: bool = True,
    configs_dir: str | None = None,
) -> DocumentText:
    """Extract text from first max_pages; OCR pages with insufficient text layer.

    Never fails because of missing OCR: pages that need OCR when Tesseract is
    unavailable fall back to text from annotations/form fields (or a sidecar
    '<name>.ocr.txt' file) and get a readable warning in DocumentText.warnings.
    """
    from odwolania2json import ocr as ocr_mod

    path = Path(pdf_path)
    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Nie można otworzyć PDF '{path.name}': {exc}") from exc
    if doc.needs_pass:
        doc.close()
        raise ValueError(f"PDF '{path.name}' jest zaszyfrowany hasłem — nie da się odczytać treści.")
    result = DocumentText(path=path, max_pages=max_pages)
    n = min(len(doc), max_pages)

    def _clean(s: str) -> str:
        return clean_ocr_page(s, configs_dir) if ocr_cleanup else fix_ocr_text(s)

    status = ocr_mod.ocr_status(ocr_lang) if ocr_enabled else {"available": False, "message": "OCR wyłączony w pipeline.yaml"}
    pages_without_text: list[int] = []

    for i in range(n):
        page = doc[i]
        text = _clean(page.get_text("text") or "")
        used_ocr = False
        method = "pdf_text"
        if len(text.strip()) < min_chars_per_page:
            has_images = bool(page.get_images())
            if status["available"]:
                try:
                    ocr_text = ocr_mod.ocr_page(page, dpi=ocr_dpi, lang=ocr_lang)
                    if len(ocr_text.strip()) > len(text.strip()):
                        text = _clean(ocr_text)
                        used_ocr = True
                        method = f"tesseract_ocr:{status.get('effective_lang')}"
                except Exception as exc:  # noqa: BLE001
                    result.warnings.append(
                        {"code": "ocr_failed", "page": i + 1, "message": f"OCR strony {i + 1} nie powiódł się: {exc}"}
                    )
            elif has_images or not text.strip():
                extra = _clean(ocr_mod.page_fallback_text(page))
                if extra.strip():
                    text = (text + "\n" + extra).strip()
                    method = "fallback_annotations"
                else:
                    method = "no_text_ocr_unavailable"
                pages_without_text.append(i + 1)
        result.pages.append(
            PageText(page_number=i + 1, text=text, char_count=len(text.strip()), used_ocr=used_ocr, method=method)
        )
    doc.close()

    if any(p.used_ocr for p in result.pages) and not status.get("lang_available"):
        result.warnings.append({"code": "ocr_lang_fallback", "message": status["message"], "hint": status.get("hint")})

    if pages_without_text:
        sidecar = path.with_suffix(".ocr.txt")
        if sidecar.exists():
            demo = document_from_text(sidecar.read_text(encoding="utf-8"), path.name, max_pages, ocr_cleanup, configs_dir)
            for p in demo.pages:
                p.method = "sidecar_text"
            result.pages = demo.pages
            result.warnings.append(
                {"code": "sidecar_text", "message": f"Użyto tekstu z pliku {sidecar.name} (tryb demonstracyjny, bez OCR)."}
            )
        else:
            result.warnings.append(
                {
                    "code": "ocr_unavailable",
                    "pages": pages_without_text,
                    "message": (
                        (f"Strona {pages_without_text[0]} wygląda" if len(pages_without_text) == 1
                         else f"Strony {', '.join(map(str, pages_without_text))} wyglądają")
                        + " na skan bez warstwy tekstowej, a OCR jest niedostępny: "
                        + status["message"].rstrip(".") + ". Wynik może być niepełny lub pusty."
                    ),
                    "hint": status.get("hint"),
                }
            )
    return result


def document_from_text(
    text: str,
    name: str = "text.txt",
    max_pages: int = 3,
    ocr_cleanup: bool = True,
    configs_dir: str | None = None,
) -> DocumentText:
    """Build a DocumentText from raw text; pages split on form feed (\\f)."""
    chunks = text.split("\f") if "\f" in text else [text]
    result = DocumentText(path=Path(name), max_pages=max_pages)
    for i, chunk in enumerate(chunks[:max_pages]):
        cleaned = clean_ocr_page(chunk, configs_dir) if ocr_cleanup else fix_ocr_text(chunk)
        result.pages.append(
            PageText(page_number=i + 1, text=cleaned, char_count=len(cleaned.strip()), method="raw_text")
        )
    return result


def page_for_span(doc_text: DocumentText, span: str | None) -> int | None:
    if not span:
        return None
    needle = span[:80]
    for p in doc_text.pages:
        if needle in p.text:
            return p.page_number
    return doc_text.pages[0].page_number if doc_text.pages else None
