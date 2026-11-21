from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from odwolania2json.case import process_case  # noqa: E402

STATUS = {"ok": "🟢", "agree": "🟢", "single": "🔵", "partial": "🟠", "warning": "🟠",
          "incomplete": "🟠", "conflict": "🔴", "missing": "⚪"}

st.set_page_config(page_title="Odwołania2json", layout="wide")
st.title("Odwołania2json")
st.caption("Lokalna ekstrakcja dokumentów sprawy KIO → kanoniczny JSON (CPU, open-source)")

uploaded = st.file_uploader("Wgraj PDF-y sprawy (jeden lub kilka)", type=["pdf"], accept_multiple_files=True)
case_id = st.text_input("Identyfikator sprawy (opcjonalnie)")

if uploaded:
    with tempfile.TemporaryDirectory() as tmp, st.spinner("Przetwarzanie…"):
        paths = []
        for i, f in enumerate(uploaded):
            p = Path(tmp) / f"{i:02d}_{Path(f.name).name}"
            p.write_bytes(f.read())
            paths.append(p)
        report = process_case(paths, case_id=case_id or None, display_names=[f.name for f in uploaded])

    st.subheader(f"{STATUS.get(report['status'], '')} Sprawa {report['case_id']}")
    st.write(f"Numer postępowania: **{report['numer_postepowania'] or '—'}**")
    c = report["summary"]["checks"]
    cols = st.columns(4)
    cols[0].metric("Dokumenty", report["summary"]["documents"])
    cols[1].metric("Kontrole zgodne", c["ok"])
    cols[2].metric("Niezgodności", c["conflict"] + c["partial"])
    cols[3].metric("Bez danych", c["missing"])

    left, right = st.columns(2)
    with left:
        st.markdown("#### Ujednolicone dane")
        st.table([
            {"pole": u["label"], "status": f"{STATUS.get(u['status'], '')} {u['status']}",
             "wartość": u["value"] if u["value"] is not None else "null"}
            for u in report["unified"].values()
        ])
    with right:
        st.markdown("#### Spójność")
        st.table([
            {"reguła": x["label"], "status": f"{STATUS.get(x['status'], '')} {x['status']}", "szczegóły": x["detail"]}
            for x in report["consistency"]
        ])

    st.download_button(
        "Pobierz raport sprawy",
        data=json.dumps({**report, "documents": [{k: v for k, v in d.items() if k != "trace"} for d in report["documents"]]},
                        ensure_ascii=False, indent=2),
        file_name=f"{report['case_id']}.case.json",
        mime="application/json",
    )

    st.markdown("### Dokumenty")
    tabs = st.tabs([f"{d['filename']} · {d['document_type']}" for d in report["documents"]])
    for tab, d in zip(tabs, report["documents"]):
        with tab:
            st.caption(
                f"typ: {d['document_type']} · pewność: {(d['confidence'] or 0):.2f} · "
                f"pola: {d['fields_filled']}/{d['fields_total']} · OCR: {'tak' if d['used_ocr'] else 'nie'}"
            )
            a, b = st.columns(2)
            with a:
                st.json(d["result"])
                st.download_button(
                    "Pobierz JSON", data=json.dumps(d["result"], ensure_ascii=False, indent=2),
                    file_name=f"{Path(d['filename']).stem}.json", mime="application/json", key=f"dl-{d['filename']}",
                )
            with b:
                rows = [
                    {"pole": f["path"], "wartość": json.dumps(f["value"], ensure_ascii=False)[:120],
                     "str.": f["page"], "reguła": f["rule_id"], "pewność": f["confidence"]}
                    for f in (d["trace"] or {}).get("fields", [])
                ]
                st.dataframe(rows, use_container_width=True)
else:
    st.info("Wgraj odwołanie, pełnomocnictwo i potwierdzenie przelewu — razem albo pojedynczo.")
