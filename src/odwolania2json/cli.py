from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from odwolania2json.config_loader import ROOT
from odwolania2json.evaluate import evaluate_trees
from odwolania2json.pipeline import process_input_tree, process_pdf

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Odwołania2json — PDF KIO → JSON")


@app.command("process-input")
def process_input_cmd(
    input: Path = typer.Option(ROOT / "input", "--input", "-i", help="Katalog wejściowy z case*/"),
    output: Path = typer.Option(ROOT / "output", "--output", "-o", help="Katalog wynikowy"),
    configs: Optional[Path] = typer.Option(None, "--configs", help="Katalog configs/"),
    no_trace: bool = typer.Option(False, "--no-trace", help="Nie zapisuj plików .trace.json"),
) -> None:
    """Przetwórz drzewo input/**/*.pdf → output/**/*.json (ta sama nazwa)."""
    results = process_input_tree(
        input_dir=input,
        output_dir=output,
        configs_dir=str(configs) if configs else None,
        write_trace=not no_trace,
    )
    typer.echo(f"Processed {len(results)} PDF(s) → {output}")
    for r in results:
        typer.echo(f"  [{r['document_type']}] {r['input']} → {r['output']}")


@app.command("process-file")
def process_file_cmd(
    pdf: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", "-o", help="Plik JSON wynikowy"),
    trace: Optional[Path] = typer.Option(None, "--trace", help="Plik śladu ekstrakcji"),
    configs: Optional[Path] = typer.Option(None, "--configs"),
) -> None:
    """Przetwórz pojedynczy PDF."""
    data, tr = process_pdf(pdf, configs_dir=str(configs) if configs else None)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if trace:
        trace.parent.mkdir(parents=True, exist_ok=True)
        trace.write_text(json.dumps(tr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"type={tr.get('document_type')} → {output}")


@app.command("eval")
def eval_cmd(
    pred: Path = typer.Option(..., "--pred", help="Katalog z predykcjami JSON"),
    gold: Path = typer.Option(..., "--gold", help="Katalog z referencyjnymi JSON"),
    report: Optional[Path] = typer.Option(None, "--report", help="Zapisz pełny raport JSON"),
) -> None:
    """Oblicz Precision / Recall / F1 względem gold."""
    summary = evaluate_trees(pred, gold)
    micro = summary["micro"]
    typer.echo(
        f"Micro  P={micro['precision']:.4f}  R={micro['recall']:.4f}  F1={micro['f1']:.4f}  "
        f"(tp={micro['tp']} fp={micro['fp']} fn={micro['fn']})"
    )
    typer.echo("Per type:")
    for t, m in summary["per_type"].items():
        typer.echo(f"  {t:16s} F1={m['f1']:.4f}  P={m['precision']:.4f}  R={m['recall']:.4f}")
    if report:
        report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        typer.echo(f"Report → {report}")


if __name__ == "__main__":
    app()
