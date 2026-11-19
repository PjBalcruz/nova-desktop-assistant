"""Listens for a wake word and prints the scores so you can judge accuracy. Ctrl+C stops it."""
from __future__ import annotations

import queue
import sys
import time

import numpy as np
import psutil
import sounddevice as sd

from app.config import load_config
from app.voice.listener import SAMPLE_RATE, find_input_device
from app.voice.wake_word import FRAME_SAMPLES, WakeWordDetector, WakeWordError


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "hey_jarvis"
    try:
        detector = WakeWordDetector(model)
        device = find_input_device(load_config().input_device)
    except (WakeWordError, ValueError) as exc:
        print(exc)
        return 1

    frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)

    def on_audio(indata, frame_count, time_info, status) -> None:
        try:
            frames.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass  # drop audio rather than fall behind

    process = psutil.Process()
    process.cpu_percent(None)  # start measuring
    last_report = time.monotonic()
    detections = 0
    print(f'Listening for "{model}". Say it normally, about an arm\'s length from the laptop.')
    print("Scores above 0.20 are printed. Press Ctrl+C to stop.")
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=FRAME_SAMPLES, device=device, callback=on_audio):
            while True:
                score = detector.process(frames.get())
                if detector.is_triggered(score):
                    detections += 1
                    print(f"*** WAKE WORD DETECTED (score {score:.2f}) *** total: {detections}")
                elif score >= 0.20:
                    print(f"    almost... score {score:.2f}")
                if time.monotonic() - last_report >= 10:
                    cpu = process.cpu_percent(None)
                    print(f"[NOVA is using {cpu:.0f}% of one CPU core while listening]")
                    last_report = time.monotonic()
    except sd.PortAudioError as exc:
        print(f"Microphone problem: {exc}")
        return 1
    except KeyboardInterrupt:
        print(f"\nStopped. Detected {detections} time(s).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())