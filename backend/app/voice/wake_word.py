"""Wake-word detection with openWakeWord (runs locally on the CPU, no internet needed)."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

FRAME_SAMPLES = 1280  # 80 ms of 16 kHz audio, the frame size openWakeWord works best with


class WakeWordError(RuntimeError):
    """The wake-word engine could not be started."""


class WakeWordDetector:
    """Replaceable wake-word engine.

    model: the name of a ready-made model (e.g. "hey_jarvis") or the path to your own
    .onnx file (e.g. the "Hey Nova" model we will train later).
    """

    def __init__(self, model: str = "hey_jarvis", threshold: float = 0.5, cooldown_s: float = 2.0) -> None:
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._last_trigger = 0.0
        try:
            from openwakeword.model import Model  # imported here so NOVA starts without it

            if Path(model).suffix.lower() in (".onnx", ".tflite"):
                self._model = Model(wakeword_models=[model], inference_framework="onnx")
                self._key = next(iter(self._model.models))  # a custom file holds just one model
            else:
                self._model = Model(inference_framework="onnx")  # loads all ready-made models
                self._key = model
        except Exception as exc:
            raise WakeWordError(f"Could not start the wake-word engine: {exc}") from exc
        if self._key not in self._model.models:
            raise WakeWordError(f"Unknown wake word '{model}'. Available: {list(self._model.models)}")

    def process(self, frame: np.ndarray) -> float:
        """Score one 80 ms int16 frame: 0.0 (no wake word) to 1.0 (certain)."""
        scores = self._model.predict(frame)
        return float(scores.get(self._key, 0.0))

    def is_triggered(self, score: float) -> bool:
        """True when the score passes the threshold, at most once per cooldown period."""
        now = time.monotonic()
        if score >= self._threshold and now - self._last_trigger >= self._cooldown_s:
            self._last_trigger = now
            return True
        return False

    def reset(self) -> None:
        """Forget the audio heard so far, so the end of the last wake phrase can't trigger again."""
        reset = getattr(self._model, "reset", None)
        if callable(reset):
            reset()
        silence = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        for _ in range(16):  # about 1.3 s of silence pushes any old audio out of the buffers
            self._model.predict(silence)
        self._last_trigger = time.monotonic()  # and ignore triggers for one cooldown period