from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from odwolania2json.build_json import build_canonical
from odwolania2json.classify import classify_document
from odwolania2json.config_loader import ROOT, load_pipeline_config, resolve_path
from odwolania2json.extract.engine import extract_fields
from odwolania2json.pdf_text import extract_pdf_text
from odwolania2json.trace import TraceCollector
from odwolania2json.validate import validate_document


def process_pdf(
    pdf_path: str | Path,
    configs_dir: str | None = None,
    write_trace: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Process a single PDF → (canonical_json, trace_dict)."""
    pipe = load_pipeline_config(configs_dir)
    configs = configs_dir or pipe.get("_configs_dir")
    trace = TraceCollector()

    doc_text = extract_pdf_text(
        pdf_path,
        max_pages=int(pipe.get("max_pages", 3)),
        min_chars_per_page=int(pipe.get("min_chars_per_page", 80)),
        ocr_enabled=bool(pipe.get("ocr_enabled", True)),
        ocr_dpi=int(pipe.get("ocr_dpi", 200)),
        ocr_lang=str(pipe.get("ocr_lang", "pol")),
    )
    trace.pages = [
        {
            "page": p.page_number,
            "char_count": p.char_count,
            "used_ocr": p.used_ocr,
            "method": p.method,
        }
        for p in doc_text.pages
    ]

    model_path = resolve_path(pipe.get("classifier_model", "models/doc_classifier.joblib"))
    clf = classify_document(doc_text.plain_text, configs_dir=configs, model_path=model_path)
    trace.document_type = clf.label
    trace.classification = {
        "label": clf.label,
        "confidence": clf.confidence,
        "method": clf.method,
        "scores": clf.scores,
    }

    if clf.label == "unknown":
        data: dict[str, Any] = {}
        trace.validation = {"ok": True, "errors": []}
        return data, trace.to_dict()

    extracted = extract_fields(clf.label, doc_text, configs_dir=configs, trace=trace)
    data = build_canonical(clf.label, extracted)
    validation = validate_document(clf.label, data, configs_dir=configs)
    trace.validation = validation
    return data, trace.to_dict()


def process_input_tree(
    input_dir: str | Path,
    output_dir: str | Path,
    configs_dir: str | None = None,
    write_trace: bool = True,
) -> list[dict[str, Any]]:
    """Mirror input/**/*.pdf → output/**/<same_name>.json"""
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    results = []
    pdfs = sorted(input_dir.rglob("*.pdf"))
    for pdf in pdfs:
        rel = pdf.relative_to(input_dir)
        out_json = output_dir / rel.with_suffix(".json")
        out_json.parent.mkdir(parents=True, exist_ok=True)
        data, trace = process_pdf(pdf, configs_dir=configs_dir)
        out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if write_trace:
            out_trace = out_json.with_suffix(".trace.json")
            out_trace.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(
            {
                "input": str(pdf),
                "output": str(out_json),
                "document_type": trace.get("document_type"),
                "ok": True,
            }
        )
    return results
