from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from odwolania2json.normalize import (
    clean_name,
    normalize_account,
    normalize_amount,
    normalize_bzp,
    normalize_date,
    normalize_krs,
    normalize_nip,
    normalize_regon,
    normalize_ted,
    normalize_transaction_id,
)


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        if not obj and prefix:
            out[prefix] = {}
            return out
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            out.update(flatten(v, key))
    elif isinstance(obj, list):
        if not obj and prefix:
            out[prefix] = []
            return out
        for i, v in enumerate(obj):
            key = f"{prefix}.{i}" if prefix else str(i)
            out.update(flatten(v, key))
    else:
        out[prefix] = obj
    return out


def _leaf(path: str) -> str:
    return path.lower().rsplit(".", 1)[-1]


def _norm_value(path: str, value: Any) -> Any:
    if value is None:
        return None
    leaf = _leaf(path)
    if isinstance(value, bool):
        return value
    if leaf == "kwota":
        return normalize_amount(value)
    if leaf in {"data", "czynnosc_dzien", "data_operacji"} or leaf.endswith("_dzien"):
        return normalize_date(str(value))
    if leaf == "nip":
        return normalize_nip(str(value))
    if leaf == "regon":
        return normalize_regon(str(value))
    if leaf == "krs":
        return normalize_krs(str(value))
    if leaf in {"na_rachunek", "z_rachunku"} or "rachunek" in leaf:
        return normalize_account(str(value))
    if leaf == "numer_bzp" or leaf.endswith("_bzp"):
        return normalize_bzp(str(value))
    if leaf == "numer_ted" or leaf.endswith("_ted"):
        return normalize_ted(str(value))
    if leaf == "numer_transakcji" or "transakcji" in leaf:
        return normalize_transaction_id(str(value))
    if isinstance(value, str):
        if leaf in {
            "nazwa",
            "tytul",
            "czynnosc_opis",
            "imie_nazwisko",
            "miejscowosc",
            "mail",
            "opis",
        }:
            v = clean_name(value)
            return v.casefold() if v else None
        return value.strip()
    if isinstance(value, float):
        return round(value, 2)
    return value


def compare_docs(pred: dict[str, Any], gold: dict[str, Any]) -> dict[str, int]:
    """Field-level TP/FP/FN for one document pair."""
    # Empty both → perfect classification empty
    if pred == {} and gold == {}:
        return {"tp": 1, "fp": 0, "fn": 0, "empty_match": 1}
    if gold == {} and pred != {}:
        # predicted content for negative
        fp = max(1, len(flatten(pred)))
        return {"tp": 0, "fp": fp, "fn": 0}
    if pred == {} and gold != {}:
        fn = max(1, len(flatten(gold)))
        return {"tp": 0, "fp": 0, "fn": fn}

    pf = flatten(pred)
    gf = flatten(gold)
    keys = set(pf) | set(gf)
    tp = fp = fn = 0
    for k in keys:
        pv = _norm_value(k, pf.get(k))
        gv = _norm_value(k, gf.get(k))
        # skip internal/empty-only noise
        if gv is None and pv is None:
            continue
        if gv is None and pv is not None:
            fp += 1
        elif gv is not None and pv is None:
            fn += 1
        elif pv == gv:
            tp += 1
        else:
            fp += 1
            fn += 1
    return {"tp": tp, "fp": fp, "fn": fn}


def f1_from_counts(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def _map_gold_name(pdf_stem: str) -> str:
    if pdf_stem == "potwierdzenie_przelewu":
        return "przelew"
    return pdf_stem


def evaluate_trees(pred_dir: str | Path, gold_dir: str | Path) -> dict[str, Any]:
    pred_dir = Path(pred_dir)
    gold_dir = Path(gold_dir)
    totals = {"tp": 0, "fp": 0, "fn": 0}
    per_type: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    per_field: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    details = []

    gold_files = sorted(gold_dir.rglob("*.json"))
    # ignore traces
    gold_files = [g for g in gold_files if not g.name.endswith(".trace.json")]

    for gf in gold_files:
        rel = gf.relative_to(gold_dir)
        pf = pred_dir / rel
        # also try same stem from pdf naming
        if not pf.exists():
            # potwierdzenie_przelewu.json vs przelew.json
            alt = pred_dir / rel.parent / f"{rel.stem}.json"
            pf = alt if alt.exists() else pf
        gold = json.loads(gf.read_text(encoding="utf-8")) if gf.exists() else {}
        pred = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}

        # detect type
        if gold == {}:
            dtype = "unknown"
        elif "OdwolanieKIO" in gold:
            dtype = "odwolanie"
        elif "mocodawca" in gold:
            dtype = "pelnomocnictwo"
        elif "przelew_bankowy" in gold:
            dtype = "przelew"
        else:
            dtype = "other"

        counts = compare_docs(pred, gold)
        for k in ("tp", "fp", "fn"):
            totals[k] += counts[k]
            per_type[dtype][k] += counts[k]

        # per-field detail
        if gold != {} and pred != {}:
            gf_flat = flatten(gold)
            pf_flat = flatten(pred)
            for key in set(gf_flat) | set(pf_flat):
                field_key = ".".join(x for x in key.split(".") if not x.isdigit())
                pv = _norm_value(key, pf_flat.get(key))
                gv = _norm_value(key, gf_flat.get(key))
                if gv is None and pv is None:
                    continue
                if gv is None and pv is not None:
                    per_field[field_key]["fp"] += 1
                elif gv is not None and pv is None:
                    per_field[field_key]["fn"] += 1
                elif pv == gv:
                    per_field[field_key]["tp"] += 1
                else:
                    per_field[field_key]["fp"] += 1
                    per_field[field_key]["fn"] += 1

        details.append({"file": str(rel), "type": dtype, **counts, **f1_from_counts(counts["tp"], counts["fp"], counts["fn"])})

    summary = {
        "micro": f1_from_counts(totals["tp"], totals["fp"], totals["fn"]),
        "per_type": {t: f1_from_counts(c["tp"], c["fp"], c["fn"]) for t, c in per_type.items()},
        "per_field": {
            f: f1_from_counts(c["tp"], c["fp"], c["fn"])
            for f, c in sorted(per_field.items(), key=lambda x: -f1_from_counts(x[1]["tp"], x[1]["fp"], x[1]["fn"])["f1"])
        },
        "files": details,
    }
    return summary
