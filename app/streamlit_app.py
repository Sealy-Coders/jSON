from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from odwolania2json.pipeline import process_pdf  # noqa: E402

st.set_page_config(page_title="Odwołania2json", layout="wide")
st.title("Odwołania2json")
st.caption("Lokalna ekstrakcja dokumentów KIO → kanoniczny JSON (CPU, open-source)")

uploaded = st.file_uploader("Wgraj PDF", type=["pdf"])
show_trace = st.checkbox("Pokaż ślad ekstrakcji (transparentność)", value=True)

if uploaded is not None:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(uploaded.read())
        tmp_path = Path(tmp.name)
    with st.spinner("Przetwarzanie…"):
        data, trace = process_pdf(tmp_path)
    tmp_path.unlink(missing_ok=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Wynik JSON")
        st.json(data)
        st.download_button(
            "Pobierz JSON",
            data=json.dumps(data, ensure_ascii=False, indent=2),
            file_name=f"{Path(uploaded.name).stem}.json",
            mime="application/json",
        )
    with col2:
        st.subheader("Klasyfikacja")
        st.write(trace.get("classification", {}))
        if show_trace:
            st.subheader("Ślad pól")
            st.json(trace)
else:
    st.info("Wgraj dokument PDF (odwołanie, pełnomocnictwo lub potwierdzenie przelewu).")
