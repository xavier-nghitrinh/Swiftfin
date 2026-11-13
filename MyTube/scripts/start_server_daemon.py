"""Daemon starter for MyTube on remote Termux server."""
import os
import subprocess
import sys
import time

def main():
    # Kill any existing uvicorn
    subprocess.run(["pkill", "-f", "uvicorn backend.main:app"], stderr=subprocess.DEVNULL)
    time.sleep(1)

    mytube_dir = os.path.expanduser("~/MyTube")
    log_path = os.path.join(mytube_dir, "mytube.log")
    
    with open(log_path, "w") as log_file:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"],
            cwd=mytube_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    print(f"MyTube server started with PID: {proc.pid}")
    time.sleep(2)
    # Check if process is still alive
    if proc.poll() is None:
        print("Server process is actively running!")
    else:
        print(f"Server process terminated with exit code {proc.returncode}. Log contents:")
        if os.path.exists(log_path):
            with open(log_path) as f:
                print(f.read())

if __name__ == "__main__":
    main()
