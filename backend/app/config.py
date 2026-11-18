"""Loads and validates nova.toml (apps, sites, Chrome profiles, search engines, microphone)."""
from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

# config.py -> app -> backend -> project root
CONFIG_PATH = Path(__file__).resolve().parents[2] / "nova.toml"


class AppEntry(BaseModel):
    start_name: str  # name as shown by Get-StartApps
    aliases: list[str] = Field(default_factory=list)
    process: str | None = None  # used to verify the app opened


class SiteEntry(BaseModel):
    url: str
    aliases: list[str] = Field(default_factory=list)


class NovaConfig(BaseModel):
    chrome_profiles: dict[str, str] = Field(default_factory=dict)
    apps: dict[str, AppEntry] = Field(default_factory=dict)
    sites: dict[str, SiteEntry] = Field(default_factory=dict)
    search: dict[str, str] = Field(default_factory=dict)
    input_device: str | None = None  # part of the microphone's name


def load_config(path: Path = CONFIG_PATH) -> NovaConfig:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return NovaConfig(
        chrome_profiles=raw.get("chrome", {}).get("profiles", {}),
        apps=raw.get("apps", {}),
        sites=raw.get("sites", {}),
        search=raw.get("search", {}),
        input_device=raw.get("audio", {}).get("input_device"),
    )