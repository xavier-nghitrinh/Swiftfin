#!/data/data/com.termux/files/usr/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$DIR/loop_runner.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[*] Stopping loop runner (PID: $PID)..."
        kill -TERM "$PID"
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            echo "[!] Process still responding, sending SIGKILL..."
            kill -9 "$PID" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
        echo "[+] Loop runner stopped."
        exit 0
    fi
    rm -f "$PID_FILE"
fi

PIDS=$(pgrep -f "python3.*loop_runner.py" || true)
if [ -n "$PIDS" ]; then
    echo "[*] Killing remaining loop_runner process(es): $PIDS"
    kill $PIDS 2>/dev/null || true
    echo "[+] Done."
else
    echo "[*] Loop runner is not currently running."
fi
