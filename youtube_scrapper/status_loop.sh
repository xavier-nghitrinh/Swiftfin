#!/data/data/com.termux/files/usr/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$DIR/loop_runner.pid"
LOG_FILE="$DIR/loop_runner.log"

echo "=================================================="
echo "          YouTube Scrapper Loop Status            "
echo "=================================================="

RUNNING=false
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[+] Status: RUNNING (PID: $PID)"
        RUNNING=true
    fi
fi

if [ "$RUNNING" = false ]; then
    PIDS=$(pgrep -f "python3.*loop_runner.py" || true)
    if [ -n "$PIDS" ]; then
        echo "[+] Status: RUNNING (PID: $PIDS)"
        RUNNING=true
    else
        echo "[-] Status: STOPPED"
    fi
fi

echo "=================================================="
if [ -f "$LOG_FILE" ]; then
    echo "Recent log output (last 20 lines):"
    echo "--------------------------------------------------"
    tail -n 20 "$LOG_FILE"
else
    echo "No log file found at $LOG_FILE"
fi
echo "=================================================="
