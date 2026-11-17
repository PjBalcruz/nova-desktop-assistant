"""Records 4 seconds, reports the volume, and plays it back so you can hear it."""
from __future__ import annotations

import sys
import tempfile
import time
import wave
import winsound
from pathlib import Path

import numpy as np
import sounddevice as sd

from app.voice.listener import SAMPLE_RATE, Recorder, find_input_device

SECONDS = 4


def main() -> int:
    name = " ".join(sys.argv[1:]).strip() or None  # e.g. "Microphone Array"
    try:
        device = find_input_device(name)
        recorder = Recorder(device)
        print(f"Speak now for {SECONDS} seconds...")
        recorder.start()
        time.sleep(SECONDS)
        audio = recorder.stop()
    except (ValueError, sd.PortAudioError) as exc:
        print(f"Microphone problem: {exc}")
        return 1

    peak = float(np.abs(audio).max()) if audio.size else 0.0
    print(f"Recorded {audio.size / SAMPLE_RATE:.1f} seconds. Peak volume: {peak:.3f}")
    if peak < 0.01:
        print("That is almost silent. Check Windows microphone permission and the mic choice.")
        return 1
    if peak > 0.98:
        print("That is clipping (too loud). Move back a little or speak softer.")

    wav_path = Path(tempfile.gettempdir()) / "nova_mic_test.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes((audio * 32767).astype(np.int16).tobytes())
    print("Playing it back...")
    winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())