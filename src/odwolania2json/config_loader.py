from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIGS = ROOT / "configs"


def resolve_path(path: str | Path, base: Path | None = None) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    base = base or ROOT
    return (base / p).resolve()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return data


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=4)
def load_pipeline_config(configs_dir: str | None = None) -> dict[str, Any]:
    base = Path(configs_dir) if configs_dir else DEFAULT_CONFIGS
    cfg = load_yaml(base / "pipeline.yaml")
    cfg["_configs_dir"] = str(base)
    cfg["_root"] = str(ROOT)
    return cfg


@lru_cache(maxsize=4)
def load_document_types(configs_dir: str | None = None) -> dict[str, Any]:
    base = Path(configs_dir) if configs_dir else DEFAULT_CONFIGS
    return load_yaml(base / "document_types.yaml")


def load_extractor_config(doc_type: str, configs_dir: str | None = None) -> dict[str, Any]:
    base = Path(configs_dir) if configs_dir else DEFAULT_CONFIGS
    types = load_document_types(str(base))
    meta = types["types"][doc_type]
    path = base / meta["extractor"]
    cfg = load_yaml(path)
    cfg["_type_meta"] = meta
    cfg["_doc_type"] = doc_type
    return cfg


def load_schema(doc_type: str, configs_dir: str | None = None) -> dict[str, Any]:
    base = Path(configs_dir) if configs_dir else DEFAULT_CONFIGS
    types = load_document_types(str(base))
    rel = types["types"][doc_type]["output_schema"]
    return load_json(base / rel)


def load_czynnosc_powod(configs_dir: str | None = None) -> list[dict[str, Any]]:
    base = Path(configs_dir) if configs_dir else DEFAULT_CONFIGS
    data = load_yaml(base / "extractors" / "czynnosc_powod.yaml")
    return list(data.get("reasons", []))
