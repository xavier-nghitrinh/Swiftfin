#!/data/data/com.termux/files/usr/bin/bash
# Start loop runner in background with wake lock
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Prevent CPU sleep on Android
if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock
    echo "[+] Acquired termux-wake-lock (CPU sleep disabled)"
fi

PID_FILE="$DIR/loop_runner.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "[!] Loop runner is already running (PID: $PID)."
        echo "    Use ./status_loop.sh to check status or ./stop_loop.sh to stop it."
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Run in background with nohup
nohup python3 loop_runner.py > /dev/null 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PID_FILE"

sleep 1
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "[+] Loop runner successfully started in background!"
    echo "    PID:       $NEW_PID"
    echo "    Interval:  2 hours break between sync runs"
    echo "    Logs:      tail -f $DIR/loop_runner.log"
    echo "    Status:    ./status_loop.sh"
    echo "    Stop:      ./stop_loop.sh"
else
    echo "[-] Failed to start loop runner. Check logs at $DIR/loop_runner.log"
    exit 1
fi
