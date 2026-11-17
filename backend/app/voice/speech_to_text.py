"""Local speech-to-text with faster-whisper (CPU only, no API key, works offline)."""
from __future__ import annotations

import os


import numpy as np

from app.voice.listener import SAMPLE_RATE

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # hides a harmless Windows warning

# A short hint so Whisper spells our app names correctly.
_PROMPT = (
    "Nova, open Discord. Open GitHub on AG. Open Gmail on MP. Open Chrome on work. "
    "Search YouTube for programming tutorials. Open Spotify, VS Code, Messenger."
)


class TranscriptionError(RuntimeError):
    """The speech model could not be loaded or run."""


class Transcriber:
    """Replaceable speech-to-text engine. The model is loaded on first use."""

    def __init__(self, model_size: str = "base.en", compute_type: str = "int8") -> None:
        self._model_size = model_size
        self._compute_type = compute_type
        self._model = None

    def load(self):
        if self._model is None:
            try:
                # Imported here so NOVA still starts if the package is missing.
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self._model_size, device="cpu", compute_type=self._compute_type
                )
            except Exception as exc:  # download, missing package, out of memory, ...
                raise TranscriptionError(f"Could not load the speech model: {exc}") from exc
        return self._model

    def transcribe(self, audio: np.ndarray) -> str:
        """Turn 16 kHz mono float32 audio into text. Returns '' if no speech was found."""
        if audio.size < SAMPLE_RATE * 0.3:  # under 0.3 seconds: nothing to transcribe
            return ""
        model = self.load()
        try:
            segments, _ = model.transcribe(
                audio,
                language="en",
                beam_size=1,  # fastest decoding, fine for short commands
                vad_filter=True,  # skip silence
                initial_prompt=_PROMPT,
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            raise TranscriptionError(f"Speech recognition failed: {exc}") from exc