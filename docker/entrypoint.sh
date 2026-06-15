#!/usr/bin/env bash
# Start a virtual X display for AI2-THOR, then run the server.
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
SCREEN="${THOR_SCREEN:-1280x1024x24}"

Xvfb "$DISPLAY" -screen 0 "$SCREEN" -nolisten tcp &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true' EXIT

# Wait for the display to come up.
for _ in $(seq 1 20); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then break; fi
    sleep 0.3
done

exec genair --host 0.0.0.0 --port "${PORT:-8001}"
