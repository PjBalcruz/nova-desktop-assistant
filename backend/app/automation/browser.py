"""Opens websites and web searches in Google Chrome, optionally in a specific profile."""
from __future__ import annotations

import difflib
import subprocess
import time
import winreg
from pathlib import Path
from urllib.parse import quote_plus

import psutil

from app.automation.app_manager import OpenResult
from app.config import NovaConfig, SiteEntry

_FALLBACK_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe",
]


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def find_chrome() -> Path | None:
    """Locate chrome.exe via the Windows registry, then common install paths."""
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, None)
                if Path(value).exists():
                    return Path(value)
        except OSError:
            continue
    return next((p for p in _FALLBACK_PATHS if p.exists()), None)


def find_site(spoken: str, config: NovaConfig) -> tuple[str, SiteEntry] | None:
    """Match what the user said to a site in nova.toml (exact alias, then close match)."""
    lookup: dict[str, tuple[str, SiteEntry]] = {}
    for key, entry in config.sites.items():
        for alias in entry.aliases:
            lookup[_normalize(alias)] = (key, entry)
    spoken = _normalize(spoken)
    if spoken in lookup:
        return lookup[spoken]
    close = difflib.get_close_matches(spoken, list(lookup), n=1, cutoff=0.8)
    return lookup[close[0]] if close else None


def _chrome_running() -> bool:
    return any((p.info["name"] or "").lower() == "chrome.exe" for p in psutil.process_iter(["name"]))


def _open_in_chrome(url: str | None, profile: str | None, config: NovaConfig, label: str) -> OpenResult:
    chrome = find_chrome()
    if chrome is None:
        return OpenResult(False, "I couldn't find Google Chrome on this computer.")

    args = [str(chrome)]
    where = "Chrome"
    if profile:
        folder = config.chrome_profiles.get(profile.lower())
        if folder is None:
            return OpenResult(False, f"I don't have a Chrome profile called {profile}. Add it to nova.toml.")
        args.append(f"--profile-directory={folder}")
        where = f"Chrome ({profile} profile)"
    if url:
        args.append(url)

    try:
        subprocess.Popen(args)
    except OSError as exc:
        return OpenResult(False, f"I couldn't start Chrome: {exc}")

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _chrome_running():
            if url is None:  # just a Chrome window, no page
                return OpenResult(True, f"{where} is open.")
            return OpenResult(True, f"{label} is open in {where}.")
        time.sleep(0.5)
    return OpenResult(False, "I started Chrome, but it didn't appear after 10 seconds.")


def open_site(spoken: str, config: NovaConfig, profile: str | None = None) -> OpenResult:
    match = find_site(spoken, config)
    if match is None:
        return OpenResult(False, f"I don't know a site called {spoken}. You can add it to nova.toml.")
    _, entry = match
    if not entry.url.startswith("https://"):  # safety: only https sites from the config
        return OpenResult(False, "That site isn't an https address, so I won't open it.")
    return _open_in_chrome(entry.url, profile, config, spoken.strip().title())


def search_web(query: str, engine: str, config: NovaConfig, profile: str | None = None) -> OpenResult:
    template = config.search.get(engine)
    if template is None:
        return OpenResult(False, f"I don't have a search engine called {engine}.")
    url = template.replace("{query}", quote_plus(query))  # user text is only ever encoded data
    return _open_in_chrome(url, profile, config, f"Your {engine.title()} search")


def open_chrome_window(config: NovaConfig, profile: str | None = None) -> OpenResult:
    return _open_in_chrome(None, profile, config, "Chrome")