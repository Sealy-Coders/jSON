from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from odwolania2json.config_loader import ROOT, load_pipeline_config
from odwolania2json.evaluate import evaluate_trees
from odwolania2json.pipeline import process_input_tree, process_pdf

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Odwołania2json — PDF KIO → JSON")

_LEVEL_ICON = {"ok": "✔", "warning": "⚠", "error": "✘", "info": "ℹ"}


def _echo_warnings(warnings: list[dict], indent: str = "    ") -> None:
    for w in warnings or []:
        icon = _LEVEL_ICON.get(w.get("severity", "warning"), "⚠")
        typer.secho(f"{indent}{icon} {w.get('message')}", fg="yellow" if w.get("severity") != "error" else "red")


def _ocr_banner() -> None:
    from odwolania2json.ocr import ocr_status

    st = ocr_status(str(load_pipeline_config().get("ocr_lang", "pol")))
    if not (st["available"] and st["lang_available"]):
        typer.secho(f"⚠ OCR: {st['message']}", fg="yellow")
        typer.secho(f"  PDF-y z warstwą tekstową działają normalnie. Instalacja OCR: {st['hint']}", fg="yellow")


@app.command("doctor")
def doctor_cmd() -> None:
    """Sprawdź środowisko: Python, pakiety, konfiguracja, model, Tesseract + język pol."""
    from odwolania2json.doctor import summary

    s = summary()
    color = {"ok": "green", "warning": "yellow", "error": "red"}
    for c in s["checks"]:
        typer.secho(f"{_LEVEL_ICON[c['level']]} {c['name']:<34} {c['message']}", fg=color[c["level"]])
        if c.get("hint"):
            typer.echo(f"    → {c['hint']}")
    if s["ok"]:
        typer.secho(f"\nGotowe do pracy ({s['warnings']} ostrzeżeń — aplikacja działa, część funkcji ograniczona).", fg="green")
    else:
        typer.secho(f"\nBłędy: {s['errors']}. Napraw powyższe i uruchom ponownie.", fg="red")
        raise typer.Exit(1)


@app.command("demo")
def demo_cmd(
    noise: float = typer.Option(0.0, "--noise", help="Symulowany szum OCR 0–0.3 (np. 0.1)"),
    seed: int = typer.Option(0, "--seed"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Zapisz raport sprawy demo (JSON)"),
) -> None:
    """Wbudowana fikcyjna sprawa — działa bez PDF-ów i bez Tesseracta."""
    from odwolania2json.demo import run_demo

    report = run_demo(noise=noise, seed=seed)
    _print_case(report)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        typer.echo(f"Raport → {output}")


@app.command("process-input")
def process_input_cmd(
    input: Path = typer.Option(ROOT / "input", "--input", "-i", help="Katalog wejściowy z case*/"),
    output: Path = typer.Option(ROOT / "output", "--output", "-o", help="Katalog wynikowy"),
    configs: Optional[Path] = typer.Option(None, "--configs", help="Katalog configs/"),
    no_trace: bool = typer.Option(False, "--no-trace", help="Nie zapisuj plików .trace.json"),
    case_report: Optional[Path] = typer.Option(
        None, "--case-report", help="Katalog na raporty spraw <case>.case.json (spójność dokumentów)"
    ),
) -> None:
    """Przetwórz drzewo input/**/*.pdf → output/**/*.json (ta sama nazwa)."""
    if not input.is_dir():
        typer.secho(f"✘ Brak katalogu wejściowego: {input}", fg="red")
        typer.echo("  Utwórz go i włóż PDF-y, np. input/case1/odwolanie.pdf")
        raise typer.Exit(2)
    if not any(input.rglob("*.pdf")):
        typer.secho(f"⚠ W {input} nie ma żadnych plików PDF — nic do zrobienia.", fg="yellow")
        raise typer.Exit(0)
    _ocr_banner()
    results = process_input_tree(
        input_dir=input,
        output_dir=output,
        configs_dir=str(configs) if configs else None,
        write_trace=not no_trace,
        case_report_dir=case_report,
    )
    typer.echo(f"Processed {len(results)} PDF(s) → {output}")
    for r in results:
        typer.echo(f"  [{r['document_type']}] {r['input']} → {r['output']}")
        for msg in r.get("warnings") or []:
            typer.secho(f"      ⚠ {msg}", fg="yellow")
    failed = [r for r in results if not r["ok"]]
    if failed:
        typer.secho(f"{len(failed)} plik(ów) z błędem — zapisano {{}} i opis błędu w .trace.json", fg="red")
    if case_report:
        typer.echo(f"Case reports → {case_report}")


_STATUS_ICON = {"ok": "✔", "partial": "≈", "conflict": "✘", "missing": "·"}


@app.command("process-case")
def process_case_cmd(
    paths: list[Path] = typer.Argument(..., exists=True, help="Pliki PDF jednej sprawy albo katalog sprawy"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Plik raportu sprawy (JSON)"),
    case_id: Optional[str] = typer.Option(None, "--case-id", help="Własny identyfikator sprawy"),
    configs: Optional[Path] = typer.Option(None, "--configs"),
) -> None:
    """Przetwórz kilka PDF jednej sprawy: typy, JSON-y, ujednolicenie i kontrola spójności."""
    from odwolania2json.case import process_case

    pdfs: list[Path] = []
    for p in paths:
        pdfs += sorted(p.glob("*.pdf")) if p.is_dir() else [p]
    if not pdfs:
        raise typer.BadParameter("Brak plików PDF")
    if case_id is None and len(paths) == 1 and paths[0].is_dir():
        case_id = paths[0].name
    _ocr_banner()
    report = process_case(pdfs, case_id=case_id, configs_dir=str(configs) if configs else None)
    _print_case(report)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        typer.echo(f"Raport → {output}")


def _print_case(report: dict) -> None:
    typer.echo(f"Sprawa {report['case_id']}  status={report['status']}  nr postępowania={report['numer_postepowania']}")
    for d in report["documents"]:
        conf = d["confidence"] or 0
        typer.echo(f"  {d['filename']:<36} {d['document_type']:<15} pewność={conf:.2f}  pola={d['fields_filled']}/{d['fields_total']}")
        _echo_warnings(d.get("warnings"))
    typer.echo("Spójność:")
    for c in report["consistency"]:
        typer.echo(f"  {_STATUS_ICON.get(c['status'], '?')} {c['label']:<60} {c['status']:<9} {c['detail']}")
    if report["suggestions"]:
        typer.echo("Propozycje uzupełnień (nie zastosowano — fill_missing: false):")
        for s in report["suggestions"]:
            typer.echo(f"  {s['filename']}: {s['path']} ← {s['suggested_value']!r} (z: {', '.join(s['from'])})")


@app.command("eval-noise")
def eval_noise_cmd(
    input: Path = typer.Option(ROOT / "input", "--input", "-i"),
    gold: Path = typer.Option(ROOT / "gold", "--gold"),
    rates: str = typer.Option("0,0.05,0.1,0.2", "--rates", help="Poziomy szumu, po przecinku"),
    seed: int = typer.Option(0, "--seed"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Tylko N pierwszych PDF (szybki test)"),
) -> None:
    """F1 przy syntetycznym szumie OCR (diakrytyki, cyfry/litery, homoglify, spacje)."""
    from odwolania2json.synthetic import eval_noise

    rows = eval_noise(input, gold, [float(r) for r in rates.split(",")], seed=seed, limit=limit)
    typer.echo("rate    P       R       F1")
    for r in rows:
        typer.echo(f"{r['rate']:<7} {r['precision']:.4f}  {r['recall']:.4f}  {r['f1']:.4f}")


@app.command("process-file")
def process_file_cmd(
    pdf: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", "-o", help="Plik JSON wynikowy"),
    trace: Optional[Path] = typer.Option(None, "--trace", help="Plik śladu ekstrakcji"),
    configs: Optional[Path] = typer.Option(None, "--configs"),
) -> None:
    """Przetwórz pojedynczy PDF."""
    _ocr_banner()
    try:
        data, tr = process_pdf(pdf, configs_dir=str(configs) if configs else None)
    except ValueError as exc:
        typer.secho(f"✘ {exc}", fg="red")
        raise typer.Exit(1) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if trace:
        trace.parent.mkdir(parents=True, exist_ok=True)
        trace.write_text(json.dumps(tr, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"type={tr.get('document_type')} → {output}")
    _echo_warnings(tr.get("warnings"), indent="  ")


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
