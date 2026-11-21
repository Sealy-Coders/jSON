#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"
cd "$ROOT"
python -m odwolania2json process-input --input "$ROOT/input" --output "$ROOT/output"
