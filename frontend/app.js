(() => {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file");
  const pickBtn = document.getElementById("pickBtn");
  const status = document.getElementById("status");
  const results = document.getElementById("results");
  const fileName = document.getElementById("fileName");
  const docType = document.getElementById("docType");
  const clfMethod = document.getElementById("clfMethod");
  const jsonOut = document.getElementById("jsonOut");
  const traceOut = document.getElementById("traceOut");
  const tracePane = document.getElementById("tracePane");
  const panes = document.querySelector(".panes");
  const downloadBtn = document.getElementById("downloadBtn");
  const traceToggle = document.getElementById("traceToggle");

  let lastPayload = null;
  let showTrace = false;

  function setStatus(text, show = true) {
    status.hidden = !show;
    status.textContent = text || "";
  }

  function typeLabel(t) {
    const map = {
      odwolanie: "odwołanie",
      pelnomocnictwo: "pełnomocnictwo",
      przelew: "przelew",
      unknown: "nieznany / negatyw → {}",
    };
    return map[t] || t || "—";
  }

  function render(payload) {
    lastPayload = payload;
    results.hidden = false;
    fileName.textContent = payload.filename || "—";
    docType.textContent = typeLabel(payload.document_type);
    const clf = payload.trace?.classification || {};
    clfMethod.textContent = clf.method
      ? `${clf.method} · conf ${Number(clf.confidence || 0).toFixed(2)}`
      : "—";
    jsonOut.textContent = JSON.stringify(payload.result ?? {}, null, 2);
    traceOut.textContent = JSON.stringify(payload.trace ?? {}, null, 2);
    tracePane.hidden = !showTrace;
    panes.classList.toggle("split", showTrace);
    traceToggle.textContent = showTrace ? "Ukryj ślad" : "Pokaż ślad";
  }

  async function processFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setStatus("Wybierz plik PDF.");
      return;
    }
    pickBtn.disabled = true;
    setStatus(`Przetwarzanie: ${file.name}…`);
    results.hidden = true;
    const body = new FormData();
    body.append("file", file, file.name);
    try {
      const res = await fetch("/api/extract", { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Błąd przetwarzania");
      render(data);
      setStatus(`Gotowe · typ: ${typeLabel(data.document_type)}`);
    } catch (err) {
      setStatus(err.message || String(err));
    } finally {
      pickBtn.disabled = false;
    }
  }

  pickBtn.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => processFile(fileInput.files?.[0]));

  ["dragenter", "dragover"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer?.files?.[0];
    processFile(file);
  });

  downloadBtn.addEventListener("click", () => {
    if (!lastPayload) return;
    const blob = new Blob(
      [JSON.stringify(lastPayload.result ?? {}, null, 2)],
      { type: "application/json" }
    );
    const a = document.createElement("a");
    const base = (lastPayload.filename || "wynik").replace(/\.pdf$/i, "");
    a.href = URL.createObjectURL(blob);
    a.download = `${base}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });

  traceToggle.addEventListener("click", () => {
    showTrace = !showTrace;
    if (lastPayload) render(lastPayload);
  });
})();
