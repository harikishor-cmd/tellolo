#!/usr/bin/env bash
# One command: ./run.sh   (mock by default; TELLOLO_PROVIDER=meta ./run.sh for real Meta calls, needs META_API_KEY in env)
cd "$(dirname "$0")"; export TELLOLO_PROVIDER="${TELLOLO_PROVIDER:-mock}"; exec python3 app.py
