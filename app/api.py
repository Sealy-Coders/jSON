"""FastAPI: upload PDF(s) → kanoniczny JSON + ślad ekstrakcji + raport sprawy + UI statyczne."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from odwolania2json.case import process_case  # noqa: E402
from odwolania2json.config_loader import load_document_types, load_pipeline_config  # noqa: E402
from odwolania2json.demo import run_demo  # noqa: E402
from odwolania2json.doctor import summary as doctor_summary  # noqa: E402
from odwolania2json.ocr import ocr_status  # noqa: E402
from odwolania2json.pipeline import process_pdf  # noqa: E402

FRONTEND = ROOT / "frontend"
MAX_FILES = 20
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

app = FastAPI(
    title="Odwołania2json",
    description="Lokalna ekstrakcja dokumentów KIO PDF → JSON",
    version="2.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _safe_name(name: str) -> str:
    base = Path(name).name
    return re.sub(r"[^\w.\-ąćęłńóśźżĄĆĘŁŃÓŚŹŻ ]", "_", base) or "plik.pdf"


async def _read_pdf(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail=f"Wymagany plik PDF: {file.filename}")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail=f"Pusty plik: {file.filename}")
    if not raw.lstrip()[:5].startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail=f"Plik {file.filename} ma rozszerzenie .pdf, ale nie jest PDF-em")
    return raw


async def _read_document(file: UploadFile) -> bytes:
    name = (file.filename or "").lower()
    suffix = Path(name).suffix
    if suffix in IMAGE_SUFFIXES:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail=f"Pusty plik: {file.filename}")
        return raw
    return await _read_pdf(file)


@app.get("/api/health")
def health() -> dict:
    pipe = load_pipeline_config()
    diag = doctor_summary()
    return {
        "status": "ok",
        "service": "odwolania2json",
        "version": app.version,
        "ocr": ocr_status(str(pipe.get("ocr_lang", "pol"))),
        "ocr_enabled": bool(pipe.get("ocr_enabled", True)),
        "doctor": diag,
    }


@app.get("/api/demo")
def demo(noise: float = Query(0.0, ge=0.0, le=0.5), seed: int = 0) -> dict:
    return run_demo(noise=noise, seed=seed)


@app.get("/api/types")
def types() -> dict:
    cfg = load_document_types()
    return {
        "types": {k: {"label": v.get("label", k)} for k, v in cfg.get("types", {}).items()},
        "unknown_label": cfg.get("unknown_label", "unknown"),
    }


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)) -> dict:
    raw = await _read_document(file)
    suffix = Path(file.filename or "").suffix.lower() or ".pdf"
    if suffix not in IMAGE_SUFFIXES:
        suffix = ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        path = Path(tmp.name)
    try:
        data, trace = process_pdf(path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)
    return {
        "filename": file.filename,
        "document_type": trace.get("document_type"),
        "result": data,
        "trace": trace,
    }


@app.post("/api/case")
async def case(files: list[UploadFile] = File(...), case_id: str | None = Form(None)) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="Brak plików")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Maksymalnie {MAX_FILES} plików na sprawę")
    with tempfile.TemporaryDirectory() as tmp:
        paths, names = [], []
        for i, f in enumerate(files):
            raw = await _read_document(f)
            name = _safe_name(f.filename or f"plik_{i}.pdf")
            suffix = Path(name).suffix.lower()
            if suffix not in IMAGE_SUFFIXES and suffix != ".pdf":
                suffix = ".pdf"
                name = name.rsplit(".", 1)[0] + suffix
            target = Path(tmp) / f"{i:02d}_{name}"
            target.write_bytes(raw)
            paths.append(target)
            names.append(name)
        try:
            return process_case(paths, case_id=case_id or None, display_names=names)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
