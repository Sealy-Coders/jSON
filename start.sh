#!/usr/bin/env bash
# Kept for compatibility — same as ./run.sh batch
exec "$(cd "$(dirname "$0")" && pwd)/run.sh" batch "$@"
