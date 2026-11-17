"""Speaks text with the built-in Windows voice (System.Speech). No extra packages needed."""
from __future__ import annotations

import os
import subprocess
import threading

# The text is passed through an environment variable, never pasted into the command,
# so spoken or typed text can't be run as PowerShell code.
_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.Speak($env:NOVA_SPEECH_TEXT)"
)
_MAX_CHARS = 500


class Speaker:
    """Replaceable speech engine: speak() to talk, stop() to cancel."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def speak(self, text: str, wait: bool = True) -> bool:
        """Speak text. Returns True if speech finished (or started, when wait=False)."""
        text = text.strip()[:_MAX_CHARS]
        if not text:
            return True
        self.stop()  # never talk over ourselves
        env = {**os.environ, "NOVA_SPEECH_TEXT": text}
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError:
            return False
        with self._lock:
            self._proc = proc
        if wait:
            return proc.wait() == 0
        return True

    def stop(self) -> None:
        """Cancel any speech in progress."""
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()