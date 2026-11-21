"""Multi-document appeal case: link documents, unify values, verify consistency.

Principles:
- each document keeps its own JSON exactly as extracted (that is what F1 measures);
- the case report adds a unified view and consistency checks on top;
- missing data is reported as "missing", never treated as a conflict and never filled
  unless `fill_missing: true` is set in configs/case_rules.yaml.
"""
from __future__ import annotations

import copy
import hashlib
import unicodedata
from pathlib import Path
from typing import Any

import regex as re

from odwolania2json.config_loader import DEFAULT_CONFIGS, load_pipeline_config, load_yaml
from odwolania2json.extract import patterns as P


def load_case_rules(configs_dir: str | None = None) -> dict[str, Any]:
    base = Path(configs_dir) if configs_dir else DEFAULT_CONFIGS
    name = load_pipeline_config(configs_dir).get("case_rules", "case_rules.yaml")
    path = base / name
    return load_yaml(path) if path.exists() else {"rules": [], "unify": {}}


# ---------------------------------------------------------------- paths

_TOKEN = re.compile(r"([^.\[\]]+)|\[(\*|\d+)\]")


def resolve_path(data: Any, path: str) -> list[Any]:
    """'Odwolujacy[0].nip', 'mocodawca[*].data.nip' → list of non-null leaf values."""
    current = [data]
    for name, idx in _TOKEN.findall(path):
        nxt: list[Any] = []
        for node in current:
            if name:
                if isinstance(node, dict) and name in node:
                    nxt.append(node[name])
            elif idx == "*":
                if isinstance(node, list):
                    nxt.extend(node)
            elif isinstance(node, list) and int(idx) < len(node):
                nxt.append(node[int(idx)])
        current = nxt
    return [v for v in current if v not in (None, "", [], {})]


def _set_path(data: dict[str, Any], path: str, value: Any) -> bool:
    tokens = _TOKEN.findall(path)
    node: Any = data
    for i, (name, idx) in enumerate(tokens):
        last = i == len(tokens) - 1
        key: Any = name if name else (int(idx) if idx != "*" else None)
        if key is None:
            return False
        if last:
            if isinstance(node, dict) or (isinstance(node, list) and isinstance(key, int) and key < len(node)):
                node[key] = value
                return True
            return False
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            return False
    return False


def _doc_values(doc: dict[str, Any], path: str) -> list[Any]:
    text = doc.get("text") or ""
    if path == "__text__":
        return [text] if text else []
    if path == "__text_postepowanie__":
        val = _postepowanie_from_text(text)
        return [val] if val else []
    return resolve_path(doc.get("result") or {}, path)


def _postepowanie_from_text(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"(?i)\bprzetargu\s+([A-Z0-9][A-Za-z0-9./\-_]{3,40}?)(?=[\s,;]|$)", text)
    if m and re.search(r"\d", m.group(1)):
        return m.group(1).rstrip(".")
    val, _ = P.extract_postepowanie(text)
    return val


# ---------------------------------------------------------------- comparison

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


_LEGAL_FORMS = [
    ("spolkazograniczonaodpowiedzialnoscia", "spzoo"),
    ("spolkaakcyjna", "sa"),
    ("spolkajawna", "spj"),
    ("spolkakomandytowa", "spk"),
    ("spolkapartnerska", "spp"),
]


def norm_name(s: Any) -> str:
    out = re.sub(r"[^a-z0-9]", "", _strip_accents(str(s).lower()))
    for long, short in _LEGAL_FORMS:
        out = out.replace(long, short)
    return out


def norm_id(s: Any) -> str:
    return re.sub(r"\D", "", str(s))


def norm_text(s: Any) -> str:
    return re.sub(r"\s+", " ", _strip_accents(str(s).lower())).strip()


def _looks_like_person(s: str) -> bool:
    return bool(re.fullmatch(r"[A-ZĄĆĘŁŃÓŚŹŻ][\w\-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][\w\-]+){1,2}", s.strip()))


def person_matches(name: str, haystack: str) -> bool:
    """Every name token appears in the haystack by its stem (tolerates Polish case endings)."""
    tokens = [t for t in norm_text(name).split() if len(t) > 1]
    words = set(re.findall(r"\w+", norm_text(haystack)))
    if not tokens:
        return False
    return all(any(w.startswith(t[: max(3, len(t) - 2)]) for w in words) for t in tokens)


def _equal(compare: str, a: Any, b: Any) -> bool:
    if compare == "equal_id":
        return bool(norm_id(a)) and norm_id(a) == norm_id(b)
    if compare == "equal_name":
        na, nb = norm_name(a), norm_name(b)
        return bool(na) and (na == nb or (min(len(na), len(nb)) >= 8 and (na in nb or nb in na)))
    if compare == "equal_amount":
        try:
            return abs(float(a) - float(b)) < 0.005
        except (TypeError, ValueError):
            return False
    if compare == "contains":
        if norm_text(a) and norm_text(a) in norm_text(b):
            return True
        return _looks_like_person(str(a)) and person_matches(str(a), str(b))
    if compare == "person_in":
        return person_matches(str(a), str(b))
    return norm_text(a) == norm_text(b)


# ---------------------------------------------------------------- case

def _docs_by_type(docs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for d in docs:
        out.setdefault(d.get("document_type") or "unknown", []).append(d)
    return out


def _check_rule(rule: dict[str, Any], by_type: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    left, right = rule["left"], rule["right"]
    entry = {
        "id": rule["id"],
        "label": rule.get("label", rule["id"]),
        "severity": rule.get("severity", "medium"),
        "compare": rule.get("compare", "equal_text"),
        "left": {"doc": left["doc"], "path": left["path"], "values": []},
        "right": {"doc": right["doc"], "path": right["path"], "values": []},
    }
    ldocs, rdocs = by_type.get(left["doc"], []), by_type.get(right["doc"], [])
    if not ldocs or not rdocs:
        missing = [t for t, ds in ((left["doc"], ldocs), (right["doc"], rdocs)) if not ds]
        return entry | {"status": "missing", "detail": f"brak dokumentu: {', '.join(missing)}"}
    lvals = [v for d in ldocs for v in _doc_values(d, left["path"])]
    rvals = [v for d in rdocs for v in _doc_values(d, right["path"])]
    entry["left"]["values"] = lvals
    entry["right"]["values"] = [v if len(str(v)) < 200 else str(v)[:200] + "…" for v in rvals]
    if not lvals or not rvals:
        side = "lewej" if not lvals else "prawej"
        return entry | {"status": "missing", "detail": f"brak wartości po {side} stronie — nie zgadujemy"}
    compare = entry["compare"]
    matched = [lv for lv in lvals if any(_equal(compare, lv, rv) for rv in rvals)]
    if len(matched) == len(lvals) or (matched and rule.get("match") == "any"):
        return entry | {"status": "ok", "detail": "zgodne"}
    if matched:
        missing_vals = [lv for lv in lvals if lv not in matched]
        return entry | {"status": "partial", "detail": f"niezgodne: {missing_vals}"}
    return entry | {"status": "conflict", "detail": "wartości się różnią"}


def _unify_field(key: str, spec: dict[str, Any], by_type: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    compare = spec.get("compare", "equal_text")
    found = []
    for src in spec.get("sources", []):
        for d in by_type.get(src["doc"], []):
            for v in _doc_values(d, src["path"]):
                found.append({"doc": src["doc"], "filename": d.get("filename"), "path": src["path"], "value": v})
    out = {"key": key, "label": spec.get("label", key), "sources": found}
    if not found:
        return out | {"status": "missing", "value": None}
    groups: list[list[dict[str, Any]]] = []
    for f in found:
        for g in groups:
            if _equal(compare, g[0]["value"], f["value"]):
                g.append(f)
                break
        else:
            groups.append([f])
    if len(groups) > 1:
        return out | {"status": "conflict", "value": None, "candidates": [g[0]["value"] for g in groups]}
    docs = {f["filename"] for f in found}
    return out | {"status": "agree" if len(docs) > 1 else "single", "value": found[0]["value"]}


def _suggestions(
    unified: dict[str, dict[str, Any]], spec: dict[str, Any], by_type: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    out = []
    for key, u in unified.items():
        if u["status"] not in ("agree", "single") or u["value"] is None:
            continue
        for src in spec.get(key, {}).get("sources", []):
            if src["path"].startswith("__") or "*" in src["path"]:
                continue
            for d in by_type.get(src["doc"], []):
                if not d.get("result"):
                    continue
                if not resolve_path(d["result"], src["path"]):
                    out.append(
                        {
                            "filename": d.get("filename"),
                            "doc": src["doc"],
                            "path": src["path"],
                            "suggested_value": u["value"],
                            "from": sorted({f["filename"] for f in u["sources"]}),
                            "applied": False,
                        }
                    )
    return out


def _case_id(given: str | None, unified: dict[str, dict[str, Any]], docs: list[dict[str, Any]]) -> str:
    if given:
        return given
    nr = unified.get("numer_postepowania", {})
    if nr.get("status") in ("agree", "single") and nr.get("value"):
        return re.sub(r"[^A-Za-z0-9]+", "-", str(nr["value"])).strip("-")
    digest = hashlib.sha1("|".join(sorted(d.get("filename") or "" for d in docs)).encode()).hexdigest()
    return f"sprawa-{digest[:8]}"


def _doc_summary(d: dict[str, Any]) -> dict[str, Any]:
    trace = d.get("trace") or {}
    fields = trace.get("fields") or []
    leaves = [v for _, v in _iter_leaves(d.get("result") or {})]
    filled = sum(v is not None for v in leaves)
    return {
        "filename": d.get("filename"),
        "document_type": d.get("document_type"),
        "confidence": (trace.get("classification") or {}).get("confidence"),
        "classification_method": (trace.get("classification") or {}).get("method"),
        "fields_filled": filled,
        "fields_total": len(leaves),
        "suppressed": sum(1 for f in fields if f.get("suppressed")),
        "validation_ok": (trace.get("validation") or {}).get("ok", True),
        "checksum_warnings": [c for c in trace.get("checks") or [] if not c.get("checksum_ok")],
        "used_ocr": any(p.get("used_ocr") for p in trace.get("pages") or []),
        "warnings": trace.get("warnings") or [],
    }


def _iter_leaves(obj: Any, prefix: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_leaves(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_leaves(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def _warning_counts(docs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in docs:
        for w in (d.get("trace") or {}).get("warnings") or []:
            counts[w.get("code", "other")] = counts.get(w.get("code", "other"), 0) + 1
    return counts


def build_case(
    docs: list[dict[str, Any]],
    case_id: str | None = None,
    configs_dir: str | None = None,
) -> dict[str, Any]:
    """docs: [{filename, result, trace, text?}] → case report (documents are not modified unless fill_missing)."""
    rules_cfg = load_case_rules(configs_dir)
    prepared = []
    for d in docs:
        dd = dict(d)
        dd["document_type"] = dd.get("document_type") or (dd.get("trace") or {}).get("document_type") or "unknown"
        prepared.append(dd)
    by_type = _docs_by_type(prepared)

    unify_spec = rules_cfg.get("unify") or {}
    unified = {k: _unify_field(k, spec, by_type) for k, spec in unify_spec.items()}
    consistency = [_check_rule(r, by_type) for r in rules_cfg.get("rules") or []]
    suggestions = _suggestions(unified, unify_spec, by_type)

    fill = bool(rules_cfg.get("fill_missing", False))
    if fill:
        for s in suggestions:
            for d in by_type.get(s["doc"], []):
                if d.get("filename") == s["filename"]:
                    d["result"] = copy.deepcopy(d["result"])
                    s["applied"] = _set_path(d["result"], s["path"], s["suggested_value"])

    counts = {st: sum(1 for c in consistency if c["status"] == st) for st in ("ok", "partial", "conflict", "missing")}
    expected = ["odwolanie", "pelnomocnictwo", "przelew"]
    duplicates = [t for t, ds in by_type.items() if t != "unknown" and len(ds) > 1]
    status = "conflict" if counts["conflict"] else ("warning" if counts["partial"] or duplicates else "ok")
    if status == "ok" and any(t not in by_type for t in expected):
        status = "incomplete"

    return {
        "case_id": _case_id(case_id, unified, prepared),
        "numer_postepowania": unified.get("numer_postepowania", {}).get("value"),
        "status": status,
        "summary": {
            "documents": len(prepared),
            "types": {t: len(ds) for t, ds in by_type.items()},
            "missing_types": [t for t in expected if t not in by_type],
            "duplicate_types": duplicates,
            "checks": counts,
            "fill_missing": fill,
            "warnings": _warning_counts(prepared),
        },
        "unified": unified,
        "consistency": consistency,
        "suggestions": suggestions,
        "documents": [
            {
                **_doc_summary(d),
                "result": d.get("result"),
                "trace": d.get("trace"),
            }
            for d in prepared
        ],
    }


def process_case(
    pdf_paths: list[str | Path],
    case_id: str | None = None,
    configs_dir: str | None = None,
    display_names: list[str] | None = None,
) -> dict[str, Any]:
    """Process several PDFs of one appeal case and build the case report."""
    from odwolania2json.pipeline import load_document, process_document_text

    docs = []
    for i, p in enumerate(pdf_paths):
        try:
            doc_text = load_document(p, configs_dir)
            data, trace = process_document_text(doc_text, configs_dir)
            text = doc_text.plain_text
        except Exception as exc:  # noqa: BLE001 — report the file, keep processing the case
            data, text = {}, ""
            trace = {"document_type": "unknown", "error": str(exc),
                     "warnings": [{"code": "processing_error", "severity": "error", "message": str(exc)}]}
        docs.append(
            {
                "filename": display_names[i] if display_names else Path(p).name,
                "result": data,
                "trace": trace,
                "text": text,
            }
        )
    if case_id is None and pdf_paths:
        parents = {Path(p).parent.name for p in pdf_paths}
        if len(parents) == 1 and not display_names:
            case_id = parents.pop()
    return build_case(docs, case_id=case_id, configs_dir=configs_dir)
