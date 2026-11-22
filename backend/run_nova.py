"""Starts NOVA without a console window. Messages go to logs/nova.log.

Background:  pythonw.exe run_nova.py
Visible:     python run_nova.py
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

HOST, PORT = "127.0.0.1", 8000
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_FILE = LOG_DIR / "nova.log"
MAX_LOG_BYTES = 1_000_000


def _open_log():
    LOG_DIR.mkdir(exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
        LOG_FILE.replace(LOG_DIR / "nova.old.log")  # keep one old log so it never grows forever
    return open(LOG_FILE, "a", buffering=1, encoding="utf-8")


def _already_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def main() -> int:
    if sys.stdout is None:  # pythonw has no console, so send all output to the log file
        sys.stdout = sys.stderr = _open_log()
    if _already_running():
        print("NOVA is already running, so this copy is exiting.")
        return 0
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # use the downloaded speech model, no internet check

    import uvicorn

    from app.main import app

    print("Starting NOVA...")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())