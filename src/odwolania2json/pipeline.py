from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from odwolania2json.build_json import build_canonical
from odwolania2json.classify import classify_document
from odwolania2json.config_loader import load_pipeline_config, resolve_path
from odwolania2json.extract.engine import extract_fields
from odwolania2json.normalize import CHECKSUMS
from odwolania2json.pdf_text import DocumentText, document_from_text, extract_pdf_text
from odwolania2json.trace import TraceCollector
from odwolania2json.validate import validate_document


def _flatten(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _flatten(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _flatten(v, f"{prefix}[{i}]")
    else:
        out.append((prefix, obj))
    return out


def checksum_flags(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Checksum results for NIP/REGON/PESEL/IBAN — informational only.

    Values are never rejected on a failed checksum: OCR may be right while the
    source document contains a typo, and the JSON must reflect the document.
    """
    flags = []
    for path, value in _flatten(data):
        if value is None:
            continue
        leaf = path.rsplit(".", 1)[-1]
        fn = CHECKSUMS.get(leaf)
        if fn is None:
            continue
        ok = fn(value)
        if ok is not None:
            flags.append({"path": path, "kind": leaf, "checksum_ok": ok})
    return flags


_CHECK_LABEL = {"nip": "NIP", "regon": "REGON", "pesel": "PESEL", "z_rachunku": "IBAN (z rachunku)", "na_rachunek": "IBAN (na rachunek)"}


def checksum_warnings(flags: list[dict[str, Any]], data: dict[str, Any]) -> list[dict[str, Any]]:
    values = dict(_flatten(data))
    out = []
    for f in flags:
        if f["checksum_ok"]:
            continue
        label = _CHECK_LABEL.get(f["kind"], f["kind"])
        out.append(
            {
                "code": "checksum_mismatch",
                "severity": "warning",
                "path": f["path"],
                "kind": f["kind"],
                "value": values.get(f["path"]),
                "message": f"{label} {values.get(f['path'])}: niezgodna suma kontrolna — wartość zachowana w JSON "
                "(dane syntetyczne / literówka w dokumencie / błąd OCR).",
            }
        )
    return out


def process_document_text(
    doc_text: DocumentText,
    configs_dir: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Classification → extraction → canonical JSON → validation for already extracted text."""
    pipe = load_pipeline_config(configs_dir)
    configs = configs_dir or pipe.get("_configs_dir")
    trace = TraceCollector()
    trace.pages = [
        {"page": p.page_number, "char_count": p.char_count, "used_ocr": p.used_ocr, "method": p.method}
        for p in doc_text.pages
    ]
    trace.warnings = [dict(w, severity=w.get("severity", "warning")) for w in doc_text.warnings]
    if not doc_text.plain_text.strip():
        trace.warnings.append(
            {"code": "no_text", "severity": "warning", "message": "Brak tekstu do analizy — dokument potraktowany jako nierozpoznany ({})."}
        )

    model_path = resolve_path(pipe.get("classifier_model", "models/doc_classifier.joblib"))
    clf = classify_document(doc_text.plain_text, configs_dir=configs, model_path=model_path)
    label = str(clf.label)
    trace.document_type = label
    trace.classification = {
        "label": label,
        "confidence": float(clf.confidence),
        "method": clf.method,
        "scores": clf.scores,
    }

    if label == "unknown":
        trace.validation = {"ok": True, "errors": []}
        return {}, trace.to_dict()

    extracted = extract_fields(label, doc_text, configs_dir=configs, trace=trace)
    data = build_canonical(label, extracted)
    trace.validation = validate_document(label, data, configs_dir=configs)
    trace.checks = checksum_flags(data)
    trace.warnings += checksum_warnings(trace.checks, data)
    return data, trace.to_dict()


def load_document(pdf_path: str | Path, configs_dir: str | None = None) -> DocumentText:
    pipe = load_pipeline_config(configs_dir)
    return extract_pdf_text(
        pdf_path,
        max_pages=int(pipe.get("max_pages", 3)),
        min_chars_per_page=int(pipe.get("min_chars_per_page", 80)),
        ocr_enabled=bool(pipe.get("ocr_enabled", True)),
        ocr_dpi=int(pipe.get("ocr_dpi", 200)),
        ocr_lang=str(pipe.get("ocr_lang", "pol")),
        configs_dir=configs_dir,
    )


def process_pdf(
    pdf_path: str | Path,
    configs_dir: str | None = None,
    write_trace: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Process a single PDF → (canonical_json, trace_dict)."""
    return process_document_text(load_document(pdf_path, configs_dir), configs_dir)


def process_text(
    text: str,
    name: str = "text.txt",
    configs_dir: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Same pipeline for raw text (tests, synthetic noise evaluation, pasted OCR)."""
    pipe = load_pipeline_config(configs_dir)
    doc = document_from_text(text, name=name, max_pages=int(pipe.get("max_pages", 3)), configs_dir=configs_dir)
    return process_document_text(doc, configs_dir)


def find_pdfs(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")


def process_input_tree(
    input_dir: str | Path,
    output_dir: str | Path,
    configs_dir: str | None = None,
    write_trace: bool = True,
    case_report_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Mirror input/**/*.pdf → output/**/<same_name>.json.

    case_report_dir: optionally also write one <case>.case.json per input folder
    (cross-document consistency). Kept outside output/ by default so the
    organizer's output tree contains only the expected JSON files.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    results = []
    per_folder: dict[Path, list[dict[str, Any]]] = {}
    for pdf in find_pdfs(input_dir):
        rel = pdf.relative_to(input_dir)
        out_json = output_dir / rel.with_suffix(".json")
        out_json.parent.mkdir(parents=True, exist_ok=True)
        try:
            doc_text = load_document(pdf, configs_dir)
            data, trace = process_document_text(doc_text, configs_dir)
            ok, error = True, None
        except Exception as exc:  # noqa: BLE001 — one broken PDF must not stop the batch
            doc_text = None
            data, ok, error = {}, False, str(exc)
            trace = {"document_type": "unknown", "error": error,
                     "warnings": [{"code": "processing_error", "severity": "error", "message": error}]}
        out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if write_trace:
            out_trace = out_json.with_suffix(".trace.json")
            out_trace.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(
            {
                "input": str(pdf),
                "output": str(out_json),
                "document_type": trace.get("document_type"),
                "ok": ok,
                "error": error,
                "warnings": [w["message"] for w in trace.get("warnings", [])],
            }
        )
        if case_report_dir and doc_text is not None:
            per_folder.setdefault(pdf.parent, []).append(
                {"filename": pdf.name, "result": data, "trace": trace, "text": doc_text.plain_text}
            )

    if case_report_dir:
        from odwolania2json.case import build_case

        report_dir = Path(case_report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        for folder, docs in per_folder.items():
            case = build_case(docs, case_id=folder.name, configs_dir=configs_dir)
            (report_dir / f"{folder.name}.case.json").write_text(
                json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return results
