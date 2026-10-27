#!/usr/bin/env bash
# One command for the recorded demo: real Meta models, fixed seed. Open the printed URL, tick consent once, and the story starts.
cd "$(dirname "$0")"; export TELLOLO_PROVIDER="${TELLOLO_PROVIDER:-meta}" PORT="${PORT:-8010}"
echo "English demo: http://localhost:$PORT/?demo=en   Hindi demo: http://localhost:$PORT/?demo=hi"
exec python3 app.py
