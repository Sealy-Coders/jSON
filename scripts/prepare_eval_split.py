#!/usr/bin/env python3
"""Mapuje dane/przyklad_* z hacknation-2026 do input/ + gold/."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dane", type=Path, required=True, help="Ścieżka do hacknation-2026/dane")
    ap.add_argument("--input", type=Path, default=Path("input"))
    ap.add_argument("--gold", type=Path, default=Path("gold"))
    ap.add_argument("--include-negatives", action="store_true", help="Dołącz dane/negatywne jako osobne case")
    args = ap.parse_args()

    dane: Path = args.dane
    if not dane.exists():
        raise SystemExit(f"Brak katalogu: {dane}")

    args.input.mkdir(parents=True, exist_ok=True)
    args.gold.mkdir(parents=True, exist_ok=True)

    cases = sorted([p for p in dane.iterdir() if p.is_dir() and p.name.startswith("przyklad_")])
    for case in cases:
        in_dir = args.input / case.name
        gold_dir = args.gold / case.name
        in_dir.mkdir(parents=True, exist_ok=True)
        gold_dir.mkdir(parents=True, exist_ok=True)
        for pdf in case.glob("*.pdf"):
            shutil.copy2(pdf, in_dir / pdf.name)
            stem = pdf.stem
            if stem == "potwierdzenie_przelewu":
                gt_name = "przelew.json"
                out_name = "potwierdzenie_przelewu.json"
            elif stem in ("odwolanie", "pelnomocnictwo"):
                gt_name = f"{stem}.json"
                out_name = f"{stem}.json"
            else:
                # negative inside case → empty gold with same basename
                gt_path = None
                out_name = f"{stem}.json"
                (gold_dir / out_name).write_text("{}\n", encoding="utf-8")
                continue
            src = case / gt_name
            if src.exists():
                shutil.copy2(src, gold_dir / out_name)
            else:
                (gold_dir / out_name).write_text("{}\n", encoding="utf-8")

    if args.include_negatives:
        neg = dane / "negatywne"
        if neg.exists():
            in_dir = args.input / "negatywne"
            gold_dir = args.gold / "negatywne"
            in_dir.mkdir(parents=True, exist_ok=True)
            gold_dir.mkdir(parents=True, exist_ok=True)
            for pdf in neg.glob("*.pdf"):
                shutil.copy2(pdf, in_dir / pdf.name)
                (gold_dir / f"{pdf.stem}.json").write_text("{}\n", encoding="utf-8")

    print(f"Prepared {len(cases)} cases → {args.input} / {args.gold}")


if __name__ == "__main__":
    main()
