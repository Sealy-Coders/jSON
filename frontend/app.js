(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const state = { files: [], report: null, selected: 0, typeLabels: {} };

  const STATUS_LABEL = {
    ok: "spójna", warning: "do sprawdzenia", conflict: "konflikt", incomplete: "niekompletna",
    agree: "zgodne", single: "1 źródło", partial: "częściowo", missing: "brak danych",
  };
  const CHECK_ICON = { ok: "✓", partial: "≈", conflict: "✕", missing: "–" };
  const CHECK_LABEL = { ok: "zgodne", partial: "częściowo", conflict: "konflikt", missing: "brak danych" };

  // ------------------------------------------------------------ helpers
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtVal = (v) => (v === null || v === undefined ? null : typeof v === "object" ? JSON.stringify(v) : String(v));
  const typeLabel = (t) => state.typeLabels[t] || (t === "unknown" ? "nierozpoznany" : t);
  const confClass = (c) => (c >= 0.75 ? "" : c >= 0.5 ? "mid" : "low");
  const jsonName = (filename) => filename.replace(/\.(pdf|txt)$/i, "") + ".json";
  const CHECK_KIND = { nip: "NIP", regon: "REGON", pesel: "PESEL", z_rachunku: "IBAN", na_rachunek: "IBAN" };
  const SEVERITY = { info: "info", warning: "warning", error: "bad" };
  const SEVERITY_ICON = { info: "ℹ", warning: "⚠", error: "✕" };

  function warningList(items) {
    return `<ul>${items
      .map((w) => `<li class="w-${esc(w.severity || "warning")}"><span class="w-icon">${SEVERITY_ICON[w.severity] || "⚠"}</span>
        <span>${w.filename ? `<b>${esc(w.filename)}</b>: ` : ""}${esc(w.message)}${w.hint ? ` <code>${esc(w.hint)}</code>` : ""}</span></li>`)
      .join("")}</ul>`;
  }

  function checksumBadge(d) {
    const bad = d.checksum_warnings || [];
    if (!bad.length) return "";
    const kinds = [...new Set(bad.map((c) => CHECK_KIND[c.kind] || c.kind))].join("/");
    return `<span class="badge warning strong" title="Niezgodna suma kontrolna — wartość ZACHOWANA w JSON, to tylko ostrzeżenie">⚠ ${esc(kinds)}: suma kontrolna ×${bad.length}</span>`;
  }

  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (t.hidden = true), 1800);
  }

  function download(name, data) {
    const blob = new Blob([JSON.stringify(data, null, 2) + "\n"], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  async function copy(data) {
    const text = JSON.stringify(data, null, 2);
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    toast("Skopiowano do schowka");
  }

  function highlight(obj) {
    const json = esc(JSON.stringify(obj, null, 2));
    return json.replace(
      /(&quot;(?:\\.|[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false)\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g,
      (m, str, colon, bool) => {
        if (str) return colon ? `<span class="k">${str}</span>${colon}` : `<span class="s">${str}</span>`;
        if (bool) return `<span class="b">${m}</span>`;
        if (m === "null") return `<span class="z">null</span>`;
        return `<span class="n">${m}</span>`;
      }
    );
  }

  function flatten(value, prefix, out) {
    if (Array.isArray(value)) {
      if (!value.length) out.push([prefix, null]);
      value.forEach((v, i) => flatten(v, `${prefix}[${i}]`, out));
    } else if (value && typeof value === "object") {
      const keys = Object.keys(value);
      if (!keys.length) out.push([prefix, null]);
      keys.forEach((k) => flatten(value[k], prefix ? `${prefix}.${k}` : k, out));
    } else {
      out.push([prefix, value]);
    }
    return out;
  }

  // ------------------------------------------------------------ API
  async function checkHealth() {
    const pill = $("#health-pill");
    try {
      const r = await fetch("/api/health");
      if (!r.ok) throw new Error();
      const h = await r.json();
      renderSystem(h);
      const t = await fetch("/api/types").then((x) => x.json());
      Object.entries(t.types || {}).forEach(([k, v]) => (state.typeLabels[k] = v.label || k));
    } catch {
      pill.textContent = "API niedostępne";
      pill.className = "pill bad";
      const b = $("#sys-banner");
      b.className = "sys-banner bad";
      b.innerHTML = `<b>Serwer nie odpowiada.</b> Uruchom go poleceniem <code>./run.sh</code> (Windows: <code>run.bat</code>) i odśwież stronę.`;
      b.hidden = false;
    }
  }

  function renderSystem(h) {
    const pill = $("#health-pill");
    const ocr = h.ocr || {};
    const ocrOk = ocr.available && ocr.lang_available;
    pill.textContent = ocrOk ? "API działa · OCR pol ✓" : ocr.available ? "API działa · OCR (bez pol)" : "API działa · bez OCR";
    pill.className = `pill ${ocrOk ? "ok" : "warn"}`;
    pill.title = ocr.message || "";
    const b = $("#sys-banner");
    const problems = ((h.doctor && h.doctor.checks) || []).filter((c) => c.level === "error");
    if (ocrOk && !problems.length) { b.hidden = true; return; }
    b.className = `sys-banner ${problems.length ? "bad" : "warn"}`;
    b.innerHTML = [
      !ocrOk ? `<div><b>OCR niedostępny — aplikacja działa dalej.</b> ${esc(ocr.message)} PDF-y z warstwą tekstową (większość dokumentów elektronicznych) są przetwarzane normalnie; skany bez tekstu dostaną ostrzeżenie i pusty/niepełny wynik. Instalacja: <code>${esc(ocr.hint)}</code></div>` : "",
      ...problems.map((c) => `<div><b>${esc(c.name)}:</b> ${esc(c.message)}${c.hint ? ` → <code>${esc(c.hint)}</code>` : ""}</div>`),
    ].join("");
    b.hidden = false;
  }

  async function request(promise, label) {
    $("#error").hidden = true;
    $("#progress").hidden = false;
    $("#progress-text").textContent = label;
    $("#run-btn").disabled = true;
    $("#demo-btn").disabled = true;
    try {
      const r = await promise();
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`);
      state.report = body;
      state.selected = Math.max(0, body.documents.findIndex((d) => d.document_type !== "unknown"));
      renderReport();
    } catch (e) {
      $("#error").textContent = `Błąd analizy: ${e.message === "Failed to fetch" ? "brak połączenia z serwerem (czy ./run.sh działa?)" : e.message}`;
      $("#error").hidden = false;
    } finally {
      $("#progress").hidden = true;
      $("#run-btn").disabled = !state.files.length;
      $("#demo-btn").disabled = false;
    }
  }

  function runCase() {
    if (!state.files.length) return;
    const fd = new FormData();
    state.files.forEach((f) => fd.append("files", f, f.name));
    const cid = $("#case-id").value.trim();
    if (cid) fd.append("case_id", cid);
    const n = state.files.length;
    return request(
      () => fetch("/api/case", { method: "POST", body: fd }),
      `Analiza ${n} ${n === 1 ? "dokumentu" : "dokumentów"}: tekst → klasyfikacja → ekstrakcja → spójność…`
    );
  }

  function runDemo() {
    const noise = $("#demo-noise").value;
    return request(() => fetch(`/api/demo?noise=${encodeURIComponent(noise)}`), "Demo: fikcyjna sprawa, 3 dokumenty…");
  }

  // ------------------------------------------------------------ upload
  function addFiles(list) {
    const documents = [...list].filter((f) => /\.(pdf|png|jpe?g|tiff?|bmp|webp)$/i.test(f.name));
    if (documents.length < list.length) toast("Pominięto pliki inne niż PDF lub obraz");
    documents.forEach((f) => {
      if (!state.files.some((x) => x.name === f.name && x.size === f.size)) state.files.push(f);
    });
    renderChips();
  }

  function renderChips() {
    const ul = $("#file-chips");
    ul.innerHTML = state.files
      .map((f, i) => `<li>${esc(f.name)} <small>${(f.size / 1024).toFixed(0)} kB</small><button data-i="${i}" title="Usuń">×</button></li>`)
      .join("");
    $("#run-btn").disabled = !state.files.length;
    $("#clear-btn").disabled = !state.files.length;
    $("#run-btn").textContent = state.files.length > 1
      ? `Analizuj sprawę (${state.files.length} plików)`
      : "Analizuj dokument";
  }

  // ------------------------------------------------------------ render: case
  function renderReport() {
    const r = state.report;
    $("#results").hidden = false;
    $("#case-id-out").textContent = r.case_id;
    $("#case-nr").textContent = r.numer_postepowania ? `Numer postępowania: ${r.numer_postepowania}` : "Numer postępowania: nie ustalono";
    const st = $("#case-status");
    st.className = `badge badge-lg ${r.status}`;
    st.textContent = `Sprawa ${STATUS_LABEL[r.status] || r.status}`;

    const s = r.summary;
    const recognized = r.documents.filter((d) => d.document_type !== "unknown").length;
    $("#case-stats").innerHTML = [
      [s.documents, "dokumentów"],
      [recognized, "rozpoznanych"],
      [s.checks.ok, "kontroli zgodnych"],
      [s.checks.conflict + s.checks.partial, "niezgodności"],
      [s.checks.missing, "bez danych do porównania"],
    ]
      .map(([v, l]) => `<div class="stat"><b>${v}</b><span>${l}</span></div>`)
      .join("") +
      (s.missing_types.length
        ? `<div class="stat"><b>${s.missing_types.length}</b><span>brakujące typy: ${s.missing_types.map(typeLabel).map(esc).join(", ")}</span></div>`
        : "");

    const warns = r.documents.flatMap((d) => (d.warnings || []).map((w) => ({ ...w, filename: d.filename })));
    const cw = $("#case-warnings");
    const important = warns.filter((w) => w.severity !== "info");
    const infos = warns.filter((w) => w.severity === "info");
    const uniqInfo = [...new Map(infos.map((w) => [w.message, { ...w, filename: null }])).values()];
    const shown = [...important, ...uniqInfo];
    cw.hidden = !shown.length;
    cw.innerHTML = shown.length
      ? `<h4>Ostrzeżenia (${important.length}) <small>— wartości nie są odrzucane, tylko oznaczone</small></h4>${warningList(shown)}`
      : "";

    renderUnified(r.unified);
    renderChecks(r.consistency, r.suggestions, s.fill_missing);
    renderTiles();
    renderDetail();
    $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderUnified(unified) {
    $("#unified").innerHTML = Object.values(unified || {})
      .map((u) => {
        const v = typeof u.value === "number" && /kwota/.test(u.key)
          ? `${u.value.toLocaleString("pl-PL", { minimumFractionDigits: 2 })} zł`
          : fmtVal(u.value);
        const src = [...new Set((u.sources || []).map((x) => x.filename))].join(", ");
        const cands = u.candidates ? `<div class="u-cands">kandydaci: ${u.candidates.map((c) => esc(fmtVal(c))).join(" · ")}</div>` : "";
        return `<div class="u-tile">
          <div class="u-head"><span class="u-label">${esc(u.label)}</span><span class="badge ${u.status}">${STATUS_LABEL[u.status] || u.status}</span></div>
          <div class="u-value ${v === null ? "null" : ""}">${v === null ? (u.status === "conflict" ? "null — dokumenty się różnią" : "null — brak danych") : esc(v)}</div>
          ${cands}
          ${src ? `<div class="u-src">źródła: ${esc(src)}</div>` : ""}
        </div>`;
      })
      .join("") || `<p class="empty">Brak reguł ujednolicania.</p>`;
  }

  function renderChecks(checks, suggestions, fillMissing) {
    $("#checks").innerHTML = (checks || [])
      .map((c) => {
        const lv = (c.left.values || []).map(fmtVal).join(", ");
        const detail = c.status === "missing" ? c.detail : `${c.detail}${lv ? ` · ${typeLabel(c.left.doc)}: ${lv}` : ""}`;
        return `<li>
          <div class="c-head"><span class="c-label">${CHECK_ICON[c.status] || "?"} ${esc(c.label)}</span><span class="badge ${c.status}">${CHECK_LABEL[c.status] || c.status}</span></div>
          <div class="c-detail">${esc(detail)}</div>
        </li>`;
      })
      .join("") || `<p class="empty">Brak reguł spójności.</p>`;

    $("#suggestions").innerHTML = suggestions && suggestions.length
      ? `<div class="suggest"><h4>Propozycje uzupełnień ${fillMissing ? "(zastosowane)" : "(nie zastosowano — fill_missing: false)"}</h4><ul>${suggestions
          .map((s) => `<li><b>${esc(s.filename)}</b>: <code>${esc(s.path)}</code> ← ${esc(fmtVal(s.suggested_value))} <small>(z: ${esc(s.from.join(", "))})</small></li>`)
          .join("")}</ul></div>`
      : "";
  }

  function renderTiles() {
    const docs = state.report.documents;
    $("#doc-tiles").innerHTML = docs
      .map((d, i) => {
        const conf = d.confidence ?? 0;
        const pct = Math.round(conf * 100);
        const fill = d.fields_total ? Math.round((d.fields_filled / d.fields_total) * 100) : 0;
        const codes = new Set((d.warnings || []).map((w) => w.code));
        const textBadge = codes.has("demo") ? `<span class="badge info">demo (tekst)</span>`
          : codes.has("ocr_unavailable") ? `<span class="badge bad" title="Skan bez warstwy tekstowej, OCR niedostępny">⚠ skan bez OCR</span>`
          : codes.has("processing_error") ? `<span class="badge bad">błąd pliku</span>`
          : d.used_ocr ? `<span class="badge info">OCR</span>` : `<span class="badge no-dot">warstwa tekstowa</span>`;
        const badges = [
          `<span class="badge t-${esc(d.document_type)}">${esc(typeLabel(d.document_type))}</span>`,
          textBadge,
          d.document_type === "unknown" ? `<span class="badge missing">JSON = {}</span>` : d.validation_ok ? `<span class="badge ok">schemat OK</span>` : `<span class="badge bad">błąd schematu</span>`,
          checksumBadge(d),
          d.suppressed ? `<span class="badge warning" title="Pola z niską pewnością ustawione na null">null ×${d.suppressed}</span>` : "",
        ].join("");
        return `<button class="doc-tile t-${esc(d.document_type)} ${i === state.selected ? "active" : ""}" data-i="${i}">
          <span class="d-name">${esc(d.filename)}</span>
          <span class="d-meta">${badges}</span>
          <span class="conf"><span class="conf-row"><span>pewność klasyfikacji</span><b>${pct}%</b></span><span class="bar ${confClass(conf)}"><span style="width:${pct}%"></span></span></span>
          ${d.document_type !== "unknown" ? `<span class="conf"><span class="conf-row"><span>wypełnione pola</span><b>${d.fields_filled}/${d.fields_total}</b></span><span class="bar"><span style="width:${fill}%"></span></span></span>` : ""}
        </button>`;
      })
      .join("");
  }

  // ------------------------------------------------------------ render: document detail
  function currentDoc() {
    return state.report && state.report.documents[state.selected];
  }

  function renderDetail() {
    const d = currentDoc();
    if (!d) return;
    $("#detail").hidden = false;
    $("#detail-name").textContent = d.filename;
    const cls = (d.trace && d.trace.classification) || {};
    $("#detail-badges").innerHTML = [
      `<span class="badge t-${esc(d.document_type)}">${esc(typeLabel(d.document_type))}</span>`,
      `<span class="badge no-dot">pewność ${Math.round((d.confidence ?? 0) * 100)}%</span>`,
      cls.method ? `<span class="badge no-dot">metoda: ${esc(cls.method)}</span>` : "",
      checksumBadge(d),
    ].join("");
    const dw = (d.warnings || []).filter((w) => w.severity !== "info");
    $("#detail-warnings").hidden = !dw.length;
    $("#detail-warnings").innerHTML = dw.length ? warningList(dw) : "";
    $("#json-view").innerHTML = highlight(d.result);
    $("#trace-view").innerHTML = highlight(d.trace);
    renderFields();
    renderClassification();
  }

  function fieldRows(d) {
    const trace = d.trace || {};
    const checks = {};
    (trace.checks || []).forEach((c) => (checks[c.path] = c.checksum_ok));
    const rows = [];
    (trace.fields || []).forEach((f) => {
      const leaves = f.value !== null && typeof f.value === "object" ? flatten(f.value, f.path, []) : [[f.path, f.value]];
      leaves.forEach(([path, value]) => rows.push({ ...f, path, value, checksum: checks[path] }));
    });
    return rows;
  }

  function markSpan(span, value) {
    const s = esc(span || "");
    const v = fmtVal(value);
    if (!v || v.length < 3) return s;
    const ev = esc(v);
    const idx = s.indexOf(ev);
    return idx < 0 ? s : `${s.slice(0, idx)}<mark>${ev}</mark>${s.slice(idx + ev.length)}`;
  }

  function renderFields() {
    const d = currentDoc();
    const body = $("#fields-body");
    if (!d || d.document_type === "unknown") {
      body.innerHTML = `<tr><td colspan="6" class="empty">Dokument nierozpoznany — wynik to pusty obiekt <code>{}</code> (zgodnie z wymaganiami). Szczegóły w zakładce „Klasyfikacja”.</td></tr>`;
      return;
    }
    const q = $("#field-filter").value.trim().toLowerCase();
    const onlyFilled = $("#only-filled").checked;
    const rows = fieldRows(d).filter((r) => {
      if (onlyFilled && (r.value === null || r.value === undefined)) return false;
      if (!q) return true;
      return [r.path, fmtVal(r.value), r.rule_id, r.source_span].some((x) => String(x ?? "").toLowerCase().includes(q));
    });
    body.innerHTML = rows
      .map((r) => {
        const v = fmtVal(r.value);
        const c = r.confidence ?? 0;
        const sup = r.suppressed ? `<span class="sup-note">odrzucono „${esc(fmtVal(r.suppressed.value))}” — ${esc(r.suppressed.reason)}</span>` : "";
        const kind = CHECK_KIND[r.path.split(".").pop()] || "suma";
        const chk = r.checksum === undefined ? ""
          : r.checksum ? ` <span class="badge ok" title="Suma kontrolna poprawna">✓ ${kind}</span>`
          : ` <span class="badge warning strong" title="Niezgodna suma kontrolna — wartość zachowana zgodnie z dokumentem (dane syntetyczne / literówka / OCR)">⚠ ${kind}: suma kontrolna</span>`;
        return `<tr class="${r.suppressed ? "suppressed" : ""} ${r.checksum === false ? "chk-warn" : ""}">
          <td class="path">${esc(r.path)}</td>
          <td class="val ${v === null ? "null" : ""}">${v === null ? "null" : esc(v)}${chk}${sup}</td>
          <td>${r.page ?? "–"}</td>
          <td class="rule">${esc(r.rule_id || r.method || "")}</td>
          <td><span class="mini-conf"><span class="bar ${confClass(c)}"><span style="width:${Math.round(c * 100)}%"></span></span><small>${c.toFixed(2)}</small></span></td>
          <td class="span">${markSpan(r.source_span, r.value)}</td>
        </tr>`;
      })
      .join("") || `<tr><td colspan="6" class="empty">Brak pól pasujących do filtra.</td></tr>`;
  }

  function renderClassification() {
    const d = currentDoc();
    const t = d.trace || {};
    const cls = t.classification || {};
    const scores = Object.entries(cls.scores || {}).filter(([, v]) => typeof v === "number");
    const max = Math.max(1e-9, ...scores.map(([, v]) => Math.abs(v)));
    $("#classification-view").innerHTML = `
      <div class="cls-meta">
        <span class="badge t-${esc(cls.label)}">${esc(typeLabel(cls.label))}</span>
        <span class="badge no-dot">pewność ${(cls.confidence ?? 0).toFixed(2)}</span>
        <span class="badge no-dot">metoda: ${esc(cls.method || "—")}</span>
      </div>
      <div class="cls-scores">${scores
        .sort((a, b) => b[1] - a[1])
        .map(([k, v]) => `<div class="cls-row"><span>${esc(k)}</span><span class="bar"><span style="width:${Math.max(0, (v / max) * 100)}%"></span></span><small>${v.toFixed(2)}</small></div>`)
        .join("") || `<p class="empty">Brak punktacji.</p>`}</div>
      <div class="pages">${(t.pages || [])
        .map((p) => `<span class="badge ${p.used_ocr ? "info" : "no-dot"}">str. ${p.page}: ${p.char_count} znaków · ${esc(p.method)}</span>`)
        .join("")}</div>`;
  }

  // ------------------------------------------------------------ events
  function bind() {
    const dz = $("#dropzone");
    const input = $("#file-input");
    dz.addEventListener("click", (e) => { if (e.target.id !== "pick-btn") input.click(); });
    $("#pick-btn").addEventListener("click", (e) => { e.stopPropagation(); input.click(); });
    dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
    input.addEventListener("change", () => { addFiles(input.files); input.value = ""; });
    ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
    dz.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

    $("#file-chips").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-i]");
      if (!b) return;
      state.files.splice(Number(b.dataset.i), 1);
      renderChips();
    });
    $("#clear-btn").addEventListener("click", () => { state.files = []; renderChips(); });
    $("#run-btn").addEventListener("click", runCase);
    $("#demo-btn").addEventListener("click", runDemo);

    $("#doc-tiles").addEventListener("click", (e) => {
      const t = e.target.closest(".doc-tile");
      if (!t) return;
      state.selected = Number(t.dataset.i);
      renderTiles();
      renderDetail();
      $("#detail").scrollIntoView({ behavior: "smooth", block: "start" });
    });

    document.querySelectorAll(".tab").forEach((tab) =>
      tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
        document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = p.dataset.panel !== tab.dataset.tab));
      })
    );
    $("#field-filter").addEventListener("input", renderFields);
    $("#only-filled").addEventListener("change", renderFields);

    $("#copy-json").addEventListener("click", () => currentDoc() && copy(currentDoc().result));
    $("#download-json").addEventListener("click", () => { const d = currentDoc(); if (d) download(jsonName(d.filename), d.result); });
    $("#copy-case").addEventListener("click", () => state.report && copy(caseExport()));
    $("#download-case").addEventListener("click", () => state.report && download(`${state.report.case_id}.case.json`, caseExport()));
    $("#download-all").addEventListener("click", () => {
      if (!state.report) return;
      state.report.documents.forEach((d, i) => setTimeout(() => download(jsonName(d.filename), d.result), i * 250));
    });
  }

  function caseExport() {
    const r = state.report;
    return { ...r, documents: r.documents.map(({ trace, ...rest }) => rest) };
  }

  bind();
  renderChips();
  checkHealth();
})();
