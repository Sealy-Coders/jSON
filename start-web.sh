#!/usr/bin/env bash
# Kept for compatibility — same as ./run.sh web (auto-reload for development)
RELOAD=1 NO_BROWSER=1 exec "$(cd "$(dirname "$0")" && pwd)/run.sh" web "$@"
