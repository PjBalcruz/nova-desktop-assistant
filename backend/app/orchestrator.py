"""Decides what a typed (later: spoken) sentence should do, and does it."""
from __future__ import annotations

import re

from app.automation import browser
from app.automation.app_manager import OpenResult, find_app, open_app
from app.config import NovaConfig
from app.parser import parse_command


def handle_text(text: str, config: NovaConfig) -> OpenResult:
    cmd = parse_command(text, set(config.chrome_profiles))
    if cmd is None:
        return OpenResult(False, "Sorry, I didn't understand that. Try: open discord")

    if cmd.kind == "search":
        return browser.search_web(cmd.target, cmd.engine, config, cmd.profile)

    # "open X": desktop apps first, then websites.
    app = find_app(cmd.target, config)
    if app is not None:
        if cmd.profile is None:
            return open_app(cmd.target, config)
        if app[0] == "chrome":
            return browser.open_chrome_window(config, cmd.profile)
        return OpenResult(False, "Profiles only apply to Chrome and websites.")

    if browser.find_site(cmd.target, config) is not None:
        return browser.open_site(cmd.target, config, cmd.profile)

    # "open work" / "open AG": a bare Chrome profile name opens Chrome in that profile.
    spoken_profile = re.sub(r"[.\s]", "", cmd.target.lower())
    if spoken_profile in config.chrome_profiles:
        return browser.open_chrome_window(config, spoken_profile)

    return OpenResult(False, f"I don't know an app or site called {cmd.target}. You can add it to nova.toml.")