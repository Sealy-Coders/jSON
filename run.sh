#!/usr/bin/env bash
# Odwołania2json — one-command start (macOS / Linux).
#   ./run.sh            → web UI on http://127.0.0.1:8000 (default)
#   ./run.sh batch      → input/**/*.pdf → output/**/*.json
#   ./run.sh case DIR   → case report for one folder of PDFs
#   ./run.sh demo       → built-in fictional case (no PDFs, no OCR needed)
#   ./run.sh doctor     → environment check
#   ./run.sh test       → pytest
#   ./run.sh eval       → batch + F1 vs gold/ + noise robustness
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
VENV="$ROOT/.venv"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

red()    { printf '\033[31m%s\033[0m\n' "$*"; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
step()   { printf '\033[1m▸ %s\033[0m\n' "$*"; }

find_python() {
  for cand in python3.13 python3.12 python3.11 python3.14 python3.15 python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      echo "$cand"; return 0
    fi
  done
  return 1
}

ensure_venv() {
  if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import sys' 2>/dev/null; then
    return
  fi
  step "Tworzę środowisko .venv"
  local py
  if ! py="$(find_python)"; then
    red "✘ Nie znaleziono Pythona ≥ 3.11."
    echo "  macOS:  brew install python@3.12"
    echo "  Ubuntu: sudo apt install python3 python3-venv"
    echo "  lub pobierz z https://www.python.org/downloads/"
    exit 1
  fi
  rm -rf "$VENV"
  if ! "$py" -m venv "$VENV"; then
    red "✘ Nie udało się utworzyć venv ($py -m venv)."
    echo "  Ubuntu/Debian: sudo apt install python3-venv"
    exit 1
  fi
}

ensure_deps() {
  local req="requirements.txt"
  [ "${1:-}" = "dev" ] && req="requirements-dev.txt"
  local stamp="$VENV/.deps-$(basename "$req" .txt)"
  local sum
  sum="$(cat requirements.txt "$req" | cksum | cut -d' ' -f1)"
  if [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$sum" ]; then
    return
  fi
  step "Instaluję zależności ($req) — tylko za pierwszym razem, zwykle kilka minut"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
  if ! "$VENV/bin/python" -m pip install --quiet -r "$req"; then
    red "✘ Instalacja pakietów nie powiodła się."
    echo "  Sprawdź połączenie z internetem (PyPI) i spróbuj ponownie: ./run.sh"
    echo "  Ręcznie: $VENV/bin/pip install -r $req"
    exit 1
  fi
  echo "$sum" > "$stamp"
}

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
PY="$VENV/bin/python"
cli() { "$PY" -m odwolania2json "$@"; }

cmd="${1:-web}"
[ $# -gt 0 ] && shift

case "$cmd" in
  -h|--help|help)
    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
    exit 0 ;;
esac

ensure_venv
case "$cmd" in
  test|eval) ensure_deps dev ;;
  *) ensure_deps ;;
esac

case "$cmd" in
  web)
    cli doctor || { red "Napraw błędy powyżej (./run.sh doctor)."; exit 1; }
    if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      red "✘ Port $PORT jest zajęty (może aplikacja już działa: http://$HOST:$PORT)."
      echo "  Inny port: PORT=8010 ./run.sh"
      exit 1
    fi
    green "▶ Interfejs: http://$HOST:$PORT   (Ctrl+C kończy)"
    if [ "${NO_BROWSER:-0}" != "1" ] && [ "$HOST" = "127.0.0.1" ]; then
      ( sleep 2; (command -v open >/dev/null && open "http://$HOST:$PORT") || (command -v xdg-open >/dev/null && xdg-open "http://$HOST:$PORT") ) >/dev/null 2>&1 &
    fi
    exec "$PY" -m uvicorn app.api:app --host "$HOST" --port "$PORT" ${RELOAD:+--reload}
    ;;
  batch)
    mkdir -p input output
    cli process-input --input "${INPUT:-$ROOT/input}" --output "${OUTPUT:-$ROOT/output}" "$@"
    ;;
  case)
    [ $# -ge 1 ] || { red "Użycie: ./run.sh case <katalog_sprawy | pliki.pdf…>"; exit 2; }
    cli process-case "$@"
    ;;
  demo)    cli demo "$@" ;;
  doctor)  cli doctor ;;
  test)    "$PY" -m pytest -q "$@" ;;
  eval)
    [ -d gold ] || { red "Brak katalogu gold/ — przygotuj: python scripts/prepare_eval_split.py --dane ../hacknation-2026/dane"; exit 2; }
    cli process-input --input input --output output --no-trace
    cli eval --pred output --gold gold
    cli eval-noise --rates "${RATES:-0,0.1,0.2}" "$@"
    ;;
  *)
    red "Nieznane polecenie: $cmd"
    echo "Dostępne: web | batch | case | demo | doctor | test | eval   (./run.sh help)"
    exit 2 ;;
esac
