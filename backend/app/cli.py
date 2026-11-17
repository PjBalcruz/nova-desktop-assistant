"""Temporary text-only runner for testing before voice input exists."""
from __future__ import annotations

import sys

from app.config import load_config
from app.orchestrator import handle_text
from app.voice.text_to_speech import Speaker


def main() -> int:
    args = sys.argv[1:]
    mute = "--mute" in args  # add --mute to skip speaking
    text = " ".join(a for a in args if a != "--mute").strip()

    result = handle_text(text, load_config())
    print(result.message)
    if not mute:
        Speaker().speak(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())