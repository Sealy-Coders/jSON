"""v2.1: works without Tesseract, clear errors, checksum warnings never drop values."""
from __future__ import annotations

import pymupdf as fitz
import pytest

from odwolania2json import ocr
from odwolania2json.demo import PRZELEW, run_demo
from odwolania2json.doctor import summary
from odwolania2json.pipeline import _flatten, process_pdf, process_text

NO_OCR = {
    "available": False,
    "lang_available": False,
    "effective_lang": None,
    "message": "Tesseract nie jest zainstalowany (test).",
    "hint": "apt install tesseract-ocr-pol",
}


def _image_only_pdf(path, text="POTWIERDZENIE PRZELEWU"):
    src = fitz.open()
    page = src.new_page()
    page.insert_text((72, 72), text, fontsize=14)
    pix = page.get_pixmap(dpi=72)
    out = fitz.open()
    p = out.new_page()
    p.insert_image(p.rect, pixmap=pix)
    out.save(path)
    return path


@pytest.fixture
def no_ocr(monkeypatch):
    monkeypatch.setattr(ocr, "ocr_status", lambda lang="pol": dict(NO_OCR, requested_lang=lang))


def test_ocr_status_never_raises():
    st = ocr.ocr_status()
    assert {"available", "lang_available", "message", "hint"} <= set(st)
    assert isinstance(st["message"], str) and st["message"]


def test_scan_without_ocr_gives_empty_json_and_warning(tmp_path, no_ocr):
    pdf = _image_only_pdf(tmp_path / "skan.pdf")
    data, trace = process_pdf(pdf, write_trace=False)
    assert data == {}
    codes = [w["code"] for w in trace["warnings"]]
    assert "ocr_unavailable" in codes and "no_text" in codes
    assert trace["pages"][0]["method"] == "no_text_ocr_unavailable"
    warn = next(w for w in trace["warnings"] if w["code"] == "ocr_unavailable")
    assert "Strona 1" in warn["message"] and warn["hint"]


def test_scan_without_ocr_uses_sidecar_text(tmp_path, no_ocr):
    pdf = _image_only_pdf(tmp_path / "przelew.pdf")
    (tmp_path / "przelew.ocr.txt").write_text(PRZELEW, encoding="utf-8")
    data, trace = process_pdf(pdf, write_trace=False)
    assert trace["document_type"] == "przelew"
    assert data
    assert any(w["code"] == "sidecar_text" for w in trace["warnings"])


def test_encrypted_pdf_has_readable_error(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "tajne")
    path = tmp_path / "haslo.pdf"
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    with pytest.raises(ValueError, match="zaszyfrowany"):
        process_pdf(path, write_trace=False)


def test_bad_iban_checksum_is_kept_with_warning():
    data, trace = process_text(PRZELEW, name="przelew.txt")
    values = dict(_flatten(data))
    ibans = {k: v for k, v in values.items() if k.endswith(("z_rachunku", "na_rachunek"))}
    assert "27114020040000300201355388" in ibans.values(), "value must not be rejected"
    warn = [w for w in trace["warnings"] if w["code"] == "checksum_mismatch"]
    assert warn and warn[0]["value"] == "27114020040000300201355388"
    assert "zachowana" in warn[0]["message"]


def test_demo_case_runs_without_pdfs():
    report = run_demo()
    assert report["case_id"] == "DEMO"
    assert {d["document_type"] for d in report["documents"]} == {"odwolanie", "pelnomocnictwo", "przelew"}
    assert report["summary"]["warnings"].get("checksum_mismatch") == 1
    przelew = next(d for d in report["documents"] if d["document_type"] == "przelew")
    assert przelew["checksum_warnings"]


def test_demo_with_noise_still_classifies():
    report = run_demo(noise=0.1)
    assert all(d["document_type"] != "unknown" for d in report["documents"])


def test_doctor_reports_ok_without_tesseract(no_ocr):
    s = summary()
    assert s["ok"], [c for c in s["checks"] if c["level"] == "error"]
