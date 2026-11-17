"""Temporary text-only runner for testing before voice exists."""
from __future__ import annotations

import sys

from app.config import load_config
from app.orchestrator import handle_text


def main() -> int:
    text = " ".join(sys.argv[1:]).strip()
    result = handle_text(text, load_config())
    print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())