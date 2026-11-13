#!/data/data/com.termux/files/usr/bin/bash
# Start MyTube server on Termux / Linux
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
else
    PY_CMD="python"
fi

export JELLYFIN_URL="${JELLYFIN_URL:-http://127.0.0.1:8096}"
export MYTUBE_HOST="${MYTUBE_HOST:-0.0.0.0}"
export MYTUBE_PORT="${MYTUBE_PORT:-8000}"

echo "=============================================="
echo "          Starting MyTube Server              "
echo "=============================================="
echo "Host:     http://${MYTUBE_HOST}:${MYTUBE_PORT}"
echo "Jellyfin: ${JELLYFIN_URL}"
echo "=============================================="

exec $PY_CMD -m uvicorn backend.main:app --host "${MYTUBE_HOST}" --port "${MYTUBE_PORT}" --reload
