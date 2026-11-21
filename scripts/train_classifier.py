#!/usr/bin/env python3
"""Trenuje lekki klasyfikator TF-IDF + LogisticRegression na CPU."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from odwolania2json.pdf_text import extract_pdf_text  # noqa: E402


def load_samples(dane: Path) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    labels: list[str] = []
    mapping = {
        "odwolanie.pdf": "odwolanie",
        "pelnomocnictwo.pdf": "pelnomocnictwo",
        "potwierdzenie_przelewu.pdf": "przelew",
    }
    for case in sorted(dane.glob("przyklad_*")):
        for name, label in mapping.items():
            pdf = case / name
            if not pdf.exists():
                continue
            doc = extract_pdf_text(pdf, max_pages=3, ocr_enabled=False)
            texts.append(doc.plain_text)
            labels.append(label)
        for pdf in case.glob("*.pdf"):
            if pdf.name in mapping:
                continue
            doc = extract_pdf_text(pdf, max_pages=3, ocr_enabled=False)
            texts.append(doc.plain_text)
            labels.append("unknown")
    neg = dane / "negatywne"
    if neg.exists():
        for pdf in neg.glob("*.pdf"):
            doc = extract_pdf_text(pdf, max_pages=3, ocr_enabled=False)
            texts.append(doc.plain_text)
            labels.append("unknown")
    return texts, labels


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dane", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "doc_classifier.joblib")
    args = ap.parse_args()

    texts, labels = load_samples(args.dane)
    if len(texts) < 10:
        raise SystemExit("Za mało próbek do treningu")

    clf = Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=2,
                    max_features=50000,
                    lowercase=True,
                ),
            ),
            (
                "lr",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    solver="lbfgs",
                ),
            ),
        ]
    )
    clf.fit(texts, labels)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, args.out)
    acc = clf.score(texts, labels)
    print(f"Saved {args.out}  train_acc={acc:.3f}  n={len(texts)}")


if __name__ == "__main__":
    main()
