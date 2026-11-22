from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

from odwolania2json.config_loader import ROOT, load_document_types, resolve_path


@dataclass
class ClassificationResult:
    label: str
    confidence: float
    method: str
    scores: dict[str, float]


def _normalize_for_match(text: str) -> str:
    t = text.lower()
    repl = {
        "ł": "l",
        "ą": "a",
        "ę": "e",
        "ó": "o",
        "ś": "s",
        "ć": "c",
        "ź": "z",
        "ż": "z",
        "ń": "n",
    }
    for a, b in repl.items():
        t = t.replace(a, b)
    # collapse spaced letterheads: "p e l n o m o c n i c t w o"
    t = re.sub(r"\b(?:[a-z]\s+){4,}[a-z]\b", lambda m: m.group(0).replace(" ", ""), t)
    t = re.sub(r"\s+", " ", t)
    return t


def rule_scores(text: str, types_cfg: dict[str, Any]) -> dict[str, float]:
    norm = _normalize_for_match(text)
    scores: dict[str, float] = {}
    for name, meta in types_cfg.get("types", {}).items():
        score = 0.0
        weight = float(meta.get("keyword_weight", 1.0))
        for kw in meta.get("keywords", []):
            k = _normalize_for_match(kw)
            if k in norm:
                # stronger if appears early
                pos = norm.find(k)
                boost = 1.5 if pos >= 0 and pos < 800 else 1.0
                score += weight * boost
        for kw in meta.get("negative_keywords", []):
            k = _normalize_for_match(kw)
            if k in norm:
                score -= 0.8 * weight
        scores[name] = score
    # Structural boosts
    if re.search(r"(?i)mocodawc|udzielam\s+pełnomocnict|ustanawiam\s+pełnomocn|pełnomocnicy", text):
        scores["pelnomocnictwo"] = scores.get("pelnomocnictwo", 0) + 2.5
    if re.search(r"(?i)potwierdzenie\s+przelewu|kwota\s+przelewu|rachunek\s+beneficjenta|tytułem", text):
        scores["przelew"] = scores.get("przelew", 0) + 2.5
    if re.search(r"(?i)wnosz[eę]\s+odwołanie|zarzut\s+nr", text):
        scores["odwolanie"] = scores.get("odwolanie", 0) + 2.0
    # Strong negative cues for non-target administrative docs
    if re.search(
        r"(?i)ogłoszenie\s+o\s+zamówieniu|dziennik\s+urz[eę]dowy|broszura|formularz\s+jpk|"
        r"wyrok|orzeczenie|skład\s+orzekający|^postanowienie\b|postanowienie\s*\n|"
        r"prowadzenie\s+postępowania\s+odwoławczego|sygn\.\s*akt|"
        r"\bdecyzja\s+nr|nie\s+służy\s+odwołanie|kodeks\w*\s+postępowania\s+administracyjnego",
        text,
    ) and not re.search(
        r"(?i)wnosz[eę]\s+(?:niniejsze\s+)?odwołanie|udzielam\s+pełnomocnict|ustanawiam\s+pełnomocn|potwierdzenie\s+przelewu",
        text,
    ):
        for k in list(scores):
            scores[k] -= 8.0
    return scores


def _load_ml(model_path: Path):
    if not model_path.exists():
        return None
    return joblib.load(model_path)


def classify_document(
    text: str,
    configs_dir: str | None = None,
    model_path: str | Path | None = None,
) -> ClassificationResult:
    types_cfg = load_document_types(configs_dir)
    unknown = types_cfg.get("unknown_label", "unknown")
    rule_thr = float(types_cfg.get("rule_confidence_threshold", 0.35))
    ml_thr = float(types_cfg.get("ml_confidence_threshold", 0.40))

    scores = rule_scores(text, types_cfg)
    ordered = sorted(scores.items(), key=lambda x: -x[1]) if scores else []
    best_label = ordered[0][0] if ordered else unknown
    best_raw = ordered[0][1] if ordered else 0.0
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    total = sum(max(0.0, v) for v in scores.values()) + 1e-6
    conf = max(0.0, best_raw) / total if best_raw > 0 else 0.0
    clear_winner = best_raw >= 2.0 and (best_raw - second) >= 0.8

    if clear_winner and conf >= rule_thr:
        return ClassificationResult(
            label=best_label,
            confidence=min(0.99, 0.55 + 0.08 * best_raw),
            method="keyword_rules",
            scores=scores,
        )

    # ML fallback (especially on close rule scores)
    path = resolve_path(model_path or "models/doc_classifier.joblib")
    model = _load_ml(path)
    if model is not None and text.strip():
        try:
            if hasattr(model, "predict_proba"):
                proba_arr = model.predict_proba([text])[0]
                classes = list(model.classes_)
                idx = int(proba_arr.argmax())
                label = classes[idx]
                conf_ml = float(proba_arr[idx])
                scores_ml = {c: float(p) for c, p in zip(classes, proba_arr)}
            else:
                label = model.predict([text])[0]
                conf_ml = 0.5
                scores_ml = {label: conf_ml}
            if label == unknown or conf_ml < ml_thr:
                # keep rule winner if reasonably strong
                if best_raw >= 2.5 and best_label != unknown:
                    return ClassificationResult(best_label, 0.6, "keyword_rules_override", scores)
                return ClassificationResult(unknown, conf_ml, "ml_classifier", scores_ml)
            return ClassificationResult(label, conf_ml, "ml_classifier", scores_ml)
        except Exception:
            pass

    if best_raw >= 1.5:
        return ClassificationResult(best_label, 0.5, "keyword_rules_weak", scores)
    return ClassificationResult(unknown, 0.0, "none", scores)
