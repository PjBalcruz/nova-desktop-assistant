"""Finds and opens Windows desktop apps, then verifies they are running."""
from __future__ import annotations

import difflib
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.config import AppEntry, NovaConfig


@dataclass
class OpenResult:
    ok: bool
    message: str  # what NOVA says back to the user


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _get_start_apps() -> list[dict[str, str]]:
    """Ask Windows for its app list: [{'Name': ..., 'AppID': ...}, ...]."""
    script = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json"
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(proc.stderr.strip() or "Get-StartApps returned nothing")
    data = json.loads(proc.stdout)
    return data if isinstance(data, list) else [data]  # one result comes back as a dict


def find_app(spoken: str, config: NovaConfig) -> tuple[str, AppEntry] | None:
    """Match what the user said to an app in nova.toml (exact alias, then close match)."""
    lookup: dict[str, tuple[str, AppEntry]] = {}
    for key, entry in config.apps.items():
        for alias in entry.aliases:
            lookup[_normalize(alias)] = (key, entry)
    spoken = _normalize(spoken)
    if spoken in lookup:
        return lookup[spoken]
    close = difflib.get_close_matches(spoken, list(lookup), n=1, cutoff=0.8)
    return lookup[close[0]] if close else None


def _launch(app_id: str) -> None:
    """Direct .exe paths run directly; everything else goes through shell:AppsFolder."""
    path = Path(app_id)
    if path.suffix.lower() == ".exe" and path.exists():
        subprocess.Popen([str(path)])
    else:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])


def _is_running(process_name: str) -> bool:
    wanted = process_name.lower()
    return any((p.info["name"] or "").lower() == wanted for p in psutil.process_iter(["name"]))


def open_app(spoken: str, config: NovaConfig, verify_timeout: float = 15.0) -> OpenResult:
    match = find_app(spoken, config)
    if match is None:
        return OpenResult(False, f"I don't know an app called {spoken}. You can add it to nova.toml.")
    _, entry = match

    try:
        installed = _get_start_apps()
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        return OpenResult(False, f"I couldn't read the list of installed apps: {exc}")

    app_id = next(
        (a["AppID"] for a in installed if a["Name"].lower() == entry.start_name.lower()), None
    )
    if app_id is None:
        return OpenResult(False, f"Windows doesn't list an app named {entry.start_name}. "
                                 "Is it installed? Check start_name in nova.toml.")

    try:
        _launch(app_id)
    except OSError as exc:
        return OpenResult(False, f"I couldn't start {entry.start_name}: {exc}")

    if not entry.process:  # nothing to check, so don't claim success
        return OpenResult(True, f"I started {entry.start_name}, but I can't confirm it opened.")

    deadline = time.monotonic() + verify_timeout
    while time.monotonic() < deadline:
        if _is_running(entry.process):
            return OpenResult(True, f"{entry.start_name} is open.")
        time.sleep(0.5)
    return OpenResult(False, f"I started {entry.start_name}, but it didn't appear "
                             f"after {verify_timeout:.0f} seconds.")