"""Speaks text with the built-in Windows voice (System.Speech). No extra packages needed.

One PowerShell worker stays running, so only the first sentence pays the start-up cost.
Text goes to the worker as plain data on stdin, never as commands.
"""
from __future__ import annotations

import subprocess
import threading

_WORKER_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$r = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), [Text.Encoding]::UTF8); "
    "[Console]::Out.WriteLine('ready'); "
    "while (($line = $r.ReadLine()) -ne $null) { $s.Speak($line); [Console]::Out.WriteLine('done') }"
)
_MAX_CHARS = 500


class Speaker:
    """Replaceable speech engine: speak() to talk (waits until finished), stop() to cancel."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._speaking: subprocess.Popen | None = None  # the worker currently talking
        self._lock = threading.Lock()

    def _start(self) -> subprocess.Popen | None:
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WORKER_SCRIPT],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError:
            return None
        if proc.stdout.readline().strip() != b"ready":  # the worker failed to start
            proc.kill()
            return None
        return proc

    def warm_up(self) -> None:
        """Start the worker now so the first sentence isn't slow."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = self._start()

    def speak(self, text: str) -> bool:
        """Speak text and wait until it has finished. Returns False if it failed or was cancelled."""
        text = " ".join(text.split())[:_MAX_CHARS]  # one line, no stray newlines
        if not text:
            return True
        self.stop()  # never talk over ourselves
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = self._start()
            proc = self._proc
            if proc is None:
                return False
            self._speaking = proc
        try:
            proc.stdin.write(text.encode("utf-8") + b"\n")
            proc.stdin.flush()
            return proc.stdout.readline().strip() == b"done"
        except OSError:
            return False
        finally:
            with self._lock:
                if self._speaking is proc:
                    self._speaking = None

    def stop(self) -> None:
        """Cancel speech in progress (the worker restarts on the next sentence)."""
        with self._lock:
            proc = self._speaking
            if proc is None:
                return
            self._speaking = None
            if self._proc is proc:
                self._proc = None
        proc.kill()