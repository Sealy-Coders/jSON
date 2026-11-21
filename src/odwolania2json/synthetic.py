"""Synthetic OCR noise for robustness tests (CPU-only, deterministic with a seed).

Noise types imitate what Tesseract does to Polish scans:
- dropped diacritics (ą→a, ł→l …) in domain words,
- digit/letter confusion in numbers (0→O, 1→l/I),
- Cyrillic homoglyphs (о, а, е, р, с),
- doubled or missing spaces.
"""
from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path
from typing import Any

import regex as re

_DIACRITICS = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
_HOMOGLYPHS = {"o": "о", "a": "а", "e": "е", "p": "р", "c": "с", "O": "О"}
_DIGIT_TO_LETTER = {"0": "O", "1": "l"}


def corrupt_text(text: str, seed: int = 0, rate: float = 0.05) -> str:
    """Return a noisy copy of text. rate ≈ share of eligible tokens/chars that get corrupted."""
    rng = random.Random(seed)

    def _word(m: re.Match) -> str:
        w = m.group(0)
        if rng.random() < rate:
            w = w.translate(_DIACRITICS)
        if rng.random() < rate / 2:
            w = "".join(_HOMOGLYPHS.get(ch, ch) if rng.random() < 0.3 else ch for ch in w)
        return w

    text = re.sub(r"\p{L}+", _word, text)

    def _number(m: re.Match) -> str:
        s = m.group(0)
        if rng.random() >= rate * 2:
            return s
        chars = list(s)
        idx = [i for i, ch in enumerate(chars) if ch in _DIGIT_TO_LETTER]
        if idx:
            i = rng.choice(idx)
            chars[i] = _DIGIT_TO_LETTER[chars[i]]
        return "".join(chars)

    text = re.sub(r"\d{6,}", _number, text)

    def _space(m: re.Match) -> str:
        r = rng.random()
        if r < rate / 3:
            return "  "
        return m.group(0)

    return re.sub(r" ", _space, text)


def eval_noise(
    input_dir: str | Path,
    gold_dir: str | Path,
    rates: list[float],
    seed: int = 0,
    configs_dir: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Extract text from PDFs once, corrupt it at each rate, run the pipeline, compute F1."""
    from odwolania2json.evaluate import evaluate_trees
    from odwolania2json.pipeline import load_document, process_text

    input_dir, gold_dir = Path(input_dir), Path(gold_dir)
    pdfs = sorted(input_dir.rglob("*.pdf"))
    if limit:
        pdfs = pdfs[:limit]
    texts = {}
    for pdf in pdfs:
        doc = load_document(pdf, configs_dir)
        texts[pdf.relative_to(input_dir)] = "\f".join(p.text for p in doc.pages)

    out = []
    for rate in rates:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for i, (rel, text) in enumerate(texts.items()):
                noisy = corrupt_text(text, seed=seed + i, rate=rate) if rate > 0 else text
                data, _ = process_text(noisy, name=rel.name, configs_dir=configs_dir)
                target = tmp_path / rel.with_suffix(".json")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            summary = evaluate_trees(tmp_path, gold_dir)
        out.append({"rate": rate, **summary["micro"], "per_type": summary["per_type"]})
    return out
