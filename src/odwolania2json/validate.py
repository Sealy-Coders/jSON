from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from odwolania2json.config_loader import load_schema


def validate_document(doc_type: str, data: dict[str, Any], configs_dir: str | None = None) -> dict[str, Any]:
    """Validate canonical JSON. Empty dict is valid for unknown/negative docs."""
    if doc_type == "unknown" or data == {}:
        return {"ok": True, "errors": []}
    schema = load_schema(doc_type, configs_dir)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    msgs = [f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors]
    return {"ok": len(msgs) == 0, "errors": msgs}
