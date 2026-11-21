"""Environment diagnostics with plain-language messages (CLI `doctor`, /api/health, run scripts)."""
from __future__ import annotations

import importlib
import sys
from typing import Any

from odwolania2json.config_loader import ROOT, load_pipeline_config, resolve_path

REQUIRED_MODULES = {
    "pymupdf": "PyMuPDF",
    "yaml": "PyYAML",
    "regex": "regex",
    "jsonschema": "jsonschema",
    "sklearn": "scikit-learn",
    "joblib": "joblib",
    "typer": "typer",
    "PIL": "Pillow",
    "numpy": "numpy",
}
OPTIONAL_MODULES = {
    "pytesseract": ("pytesseract", "OCR skanów"),
    "cv2": ("opencv-python-headless", "lepszy preprocessing OCR"),
    "fastapi": ("fastapi", "interfejs WWW"),
    "uvicorn": ("uvicorn", "serwer WWW"),
    "python_multipart": ("python-multipart", "upload plików w UI"),
}
MIN_PYTHON = (3, 11)


def _check(name: str, ok: bool, message: str, level: str = "error", hint: str | None = None) -> dict[str, Any]:
    return {"name": name, "ok": ok, "level": "ok" if ok else level, "message": message, "hint": None if ok else hint}


def run_checks() -> list[dict[str, Any]]:
    checks = []
    v = sys.version_info
    checks.append(
        _check(
            "python",
            v >= MIN_PYTHON,
            f"Python {v.major}.{v.minor}.{v.micro}",
            hint=f"Wymagany Python ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]} (python.org)",
        )
    )
    missing = []
    for mod, pkg in REQUIRED_MODULES.items():
        try:
            importlib.import_module(mod)
        except Exception:  # noqa: BLE001
            missing.append(pkg)
    checks.append(
        _check(
            "pakiety",
            not missing,
            "Wszystkie wymagane pakiety zainstalowane" if not missing else f"Brak pakietów: {', '.join(missing)}",
            hint="pip install -r requirements.txt",
        )
    )
    for mod, (pkg, purpose) in OPTIONAL_MODULES.items():
        try:
            importlib.import_module(mod)
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
        checks.append(
            _check(f"opcjonalnie: {pkg}", ok, f"{pkg} ({purpose})" + ("" if ok else " — brak"), "warning", f"pip install {pkg}")
        )

    try:
        pipe = load_pipeline_config()
        checks.append(_check("konfiguracja", True, f"configs/ wczytane ({ROOT / 'configs'})"))
    except Exception as exc:  # noqa: BLE001
        pipe = {}
        checks.append(_check("konfiguracja", False, f"Błąd configs/pipeline.yaml: {exc}", hint="Sprawdź składnię YAML"))

    model = resolve_path(pipe.get("classifier_model", "models/doc_classifier.joblib"))
    checks.append(
        _check(
            "model klasyfikatora",
            model.exists(),
            f"{model.relative_to(ROOT) if model.is_relative_to(ROOT) else model}"
            + ("" if model.exists() else " — brak, działa sam klasyfikator słów kluczowych"),
            "warning",
            "python scripts/train_classifier.py",
        )
    )

    try:
        from odwolania2json.ocr import ocr_status

        st = ocr_status(str(pipe.get("ocr_lang", "pol")))
        level = "warning"
        checks.append(_check("OCR (Tesseract)", bool(st["available"] and st["lang_available"]), st["message"], level, st["hint"]))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("OCR (Tesseract)", False, f"Nie udało się sprawdzić OCR: {exc}", "warning"))
    return checks


def summary(checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    checks = checks if checks is not None else run_checks()
    errors = [c for c in checks if c["level"] == "error"]
    warnings = [c for c in checks if c["level"] == "warning"]
    return {"ok": not errors, "errors": len(errors), "warnings": len(warnings), "checks": checks}
