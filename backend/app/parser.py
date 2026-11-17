"""Turns a sentence like 'Nova, open GitHub on AG.' into a structured Command."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Command:
    kind: str  # "open" or "search"
    target: str = ""  # what to open, or the search text
    engine: str = "google"  # search engine (for searches)
    profile: str | None = None  # spoken Chrome profile name, if one was said


_WAKE = re.compile(r"^(?:hey\s+)?nova\b[,.!]?\s*", re.IGNORECASE)
_POLITE = re.compile(r"^(?:please|can you|could you)\s+", re.IGNORECASE)

_OPEN_AND_SEARCH = re.compile(r"^open\s+(google|youtube)\s+and\s+search\s+(?:for\s+)?(.+)$", re.IGNORECASE)
_SEARCH_ENGINE_FOR = re.compile(r"^search\s+(google|youtube)\s+for\s+(.+)$", re.IGNORECASE)
_SEARCH_FOR_ON = re.compile(r"^search\s+(?:for\s+)?(.+?)\s+on\s+(google|youtube)$", re.IGNORECASE)
_SEARCH = re.compile(r"^search\s+(?:for\s+)?(.+)$", re.IGNORECASE)
_OPEN = re.compile(r"^(?:open|launch|start|run)\s+(?:up\s+)?(?:the\s+)?(.+)$", re.IGNORECASE)
_PROFILE = re.compile(
    r"^(.+?)\s+(?:on|in|with|using)\s+(?:my\s+)?(.+?)(?:\s+(?:profile|account))?$", re.IGNORECASE
)


def parse_command(text: str, profile_names: set[str]) -> Command | None:
    """Return a Command, or None if we don't understand the sentence.

    profile_names: the spoken Chrome profile names from nova.toml (lowercase).
    """
    text = _WAKE.sub("", text.strip())
    text = _POLITE.sub("", text).rstrip(".!? ")

    if m := _OPEN_AND_SEARCH.match(text):
        return Command("search", target=m.group(2).strip(), engine=m.group(1).lower())
    if m := _SEARCH_ENGINE_FOR.match(text):
        return Command("search", target=m.group(2).strip(), engine=m.group(1).lower())
    if m := _SEARCH_FOR_ON.match(text):
        return Command("search", target=m.group(1).strip(), engine=m.group(2).lower())
    if m := _SEARCH.match(text):
        return Command("search", target=m.group(1).strip())

    if m := _OPEN.match(text):
        target, profile = m.group(1).strip(), None
        p = _PROFILE.match(target)
        if p:
            # Speech often turns "AG" into "A.G." or "E.G.", so drop dots and spaces first.
            spoken_profile = re.sub(r"[.\s]", "", p.group(2).lower())
            if spoken_profile in profile_names:  # only known profile names count
                target, profile = p.group(1).strip(), spoken_profile
        return Command("open", target=target, profile=profile)

    return None