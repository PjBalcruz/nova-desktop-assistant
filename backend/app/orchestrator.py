"""Decides what a typed (later: spoken) sentence should do, and does it."""
from __future__ import annotations

import re

from app.automation import browser, system_controls, window_manager
from app.automation.app_manager import OpenResult, find_app, open_app
from app.config import NovaConfig
from app.parser import parse_command


def _open(target: str, profile: str | None, config: NovaConfig) -> OpenResult:
    """Open a desktop app, then a website, then a bare Chrome profile name."""
    app = find_app(target, config)
    if app is not None:
        if profile is None:
            return open_app(target, config)
        if app[0] == "chrome":
            return browser.open_chrome_window(config, profile)
        return OpenResult(False, "Profiles only apply to Chrome and websites.")

    if browser.find_site(target, config) is not None:
        return browser.open_site(target, config, profile)

    # "open work" / "open AG": a bare Chrome profile name opens Chrome in that profile.
    spoken_profile = re.sub(r"[.\s]", "", target.lower())
    if spoken_profile in config.chrome_profiles:
        return browser.open_chrome_window(config, spoken_profile)

    return OpenResult(False, f"I don't know an app or site called {target}. You can add it to nova.toml.")


def handle_text(text: str, config: NovaConfig) -> OpenResult:
    cmd = parse_command(text, set(config.chrome_profiles))
    if cmd is None:
        return OpenResult(False, "Sorry, I didn't understand that. Try: open discord")

    if cmd.kind == "screenshot":
        return system_controls.take_screenshot()
    if cmd.kind == "volume":
        return system_controls.adjust_volume(cmd.target, cmd.amount)
    if cmd.kind == "search":
        return browser.search_web(cmd.target, cmd.engine, config, cmd.profile)
    if cmd.kind == "window":
        if cmd.action == "switch" and find_app(cmd.target, config) is None:
            return _open(cmd.target, None, config)  # "go to youtube" opens the site
        return window_manager.control_window(cmd.action, cmd.target or None, config)
    return _open(cmd.target, cmd.profile, config)