"""Records audio from the microphone (16 kHz mono, which is what Whisper expects)."""
from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def find_input_device(name_part: str | None) -> int | None:
    """Index of the first MME input device whose name contains name_part.

    None means "use the Windows default microphone". Raises ValueError if a name
    was given but no matching microphone exists.
    """
    if not name_part:
        return None
    hostapis = sd.query_hostapis()
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] < 1:
            continue
        if hostapis[dev["hostapi"]]["name"] != "MME":
            continue
        if name_part.lower() in dev["name"].lower():
            return index
    raise ValueError(f"No microphone found with '{name_part}' in its name.")


class Recorder:
    """Push-to-talk recorder: start() when the button goes down, stop() when it's released."""

    def __init__(self, device: int | None = None) -> None:
        self._device = device
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._stream is not None:
            return
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self._device,
            callback=self._on_audio,
        )
        self._stream.start()

    def _on_audio(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        with self._lock:
            self._chunks.append(indata.copy())

    def stop(self) -> np.ndarray:
        """Stop recording; returns a 1-D float32 array (empty if nothing was recorded)."""
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        with self._lock:
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)[:, 0]