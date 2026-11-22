"""Turns a sentence like 'Nova, open GitHub on AG.' into a structured Command."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Command:
    kind: str  # "open", "search", "volume" or "screenshot"
    target: str = ""  # what to open, the search text, or the volume action (up/down/set/mute/unmute/get)
    engine: str = "google"  # search engine (for searches)
    profile: str | None = None  # spoken Chrome profile name, if one was said
    amount: int | None = None  # a number the user said (volume percent)


_WAKE = re.compile(r"^(?:hey\s+)?nova\b[,.!]?\s*", re.IGNORECASE)
_POLITE = re.compile(r"^(?:please|can you|could you)\s+", re.IGNORECASE)

_PCT = r"(?:\s+(?:by\s+)?(\d{1,3})\s*(?:%|percent)?)?"
_SCREENSHOT = re.compile(
    r"^(?:(?:take|grab|capture|make)\s+(?:a\s+|the\s+)?)?(?:screenshot|screen\s?shot|screen capture)$"
    r"|^(?:capture|grab)\s+(?:the\s+)?screen$",
    re.IGNORECASE,
)
_MUTE = re.compile(r"^(mute|unmute)(?:\s+(?:the\s+)?(?:volume|sound|audio|speakers?|it))?$", re.IGNORECASE)
_VOLUME_GET = re.compile(r"^what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?volume(?:\s+level)?$", re.IGNORECASE)
_VOLUME_SET = re.compile(
    r"^(?:(?:set|change|make)\s+)?(?:the\s+)?volume\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)?$", re.IGNORECASE
)
_VOLUME_DIR = re.compile(
    r"^(?:(?:turn|put|bring|take|crank)\s+)?(?:the\s+)?volume\s+(up|down)" + _PCT + r"(?:\s+a\s+(?:bit|little|lot))?$",
    re.IGNORECASE,
)
_VOLUME_VERB = re.compile(
    r"^(raise|increase|lower|decrease|reduce)\s+(?:the\s+)?volume" + _PCT + r"(?:\s+a\s+(?:bit|little|lot))?$",
    re.IGNORECASE,
)

_OPEN_AND_SEARCH = re.compile(r"^open\s+(google|youtube)\s+and\s+search\s+(?:for\s+)?(.+)$", re.IGNORECASE)
_SEARCH_ENGINE_FOR = re.compile(r"^search\s+(google|youtube)\s+for\s+(.+)$", re.IGNORECASE)
_SEARCH_FOR_ON = re.compile(r"^search\s+(?:for\s+)?(.+?)\s+on\s+(google|youtube)$", re.IGNORECASE)
_SEARCH = re.compile(r"^search\s+(?:for\s+)?(.+)$", re.IGNORECASE)
_OPEN = re.compile(r"^(?:open|launch|start|run)\s+(?:up\s+)?(?:the\s+)?(.+)$", re.IGNORECASE)
_PROFILE = re.compile(
    r"^(.+?)\s+(?:on|in|with|using)\s+(?:my\s+)?(.+?)(?:\s+(?:profile|account))?$", re.IGNORECASE
)


def _number(value: str | None) -> int | None:
    return int(value) if value else None


def parse_command(text: str, profile_names: set[str]) -> Command | None:
    """Return a Command, or None if we don't understand the sentence.

    profile_names: the spoken Chrome profile names from nova.toml (lowercase).
    """
    text = _WAKE.sub("", text.strip())
    text = _POLITE.sub("", text).rstrip(".!? ")

    if _SCREENSHOT.match(text):
        return Command("screenshot")
    if m := _MUTE.match(text):
        return Command("volume", target=m.group(1).lower())
    if _VOLUME_GET.match(text):
        return Command("volume", target="get")
    if m := _VOLUME_SET.match(text):
        return Command("volume", target="set", amount=int(m.group(1)))
    if m := _VOLUME_DIR.match(text):
        return Command("volume", target=m.group(1).lower(), amount=_number(m.group(2)))
    if m := _VOLUME_VERB.match(text):
        direction = "up" if m.group(1).lower() in ("raise", "increase") else "down"
        return Command("volume", target=direction, amount=_number(m.group(2)))

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