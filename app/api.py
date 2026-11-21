"""FastAPI: upload PDF → kanoniczny JSON + ślad ekstrakcji + UI statyczne."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from odwolania2json.pipeline import process_pdf  # noqa: E402

FRONTEND = ROOT / "frontend"

app = FastAPI(
    title="Odwołania2json",
    description="Lokalna ekstrakcja dokumentów KIO PDF → JSON",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "odwolania2json"}


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Wymagany plik PDF")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Pusty plik")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(raw)
        path = Path(tmp.name)
    try:
        data, trace = process_pdf(path)
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
