"""Records 5 seconds and shows what Whisper heard, with timing and memory use."""
from __future__ import annotations

import sys
import time

import psutil
import sounddevice as sd

from app.voice.listener import Recorder, find_input_device
from app.voice.speech_to_text import Transcriber, TranscriptionError

SECONDS = 5


def main() -> int:
    name = " ".join(sys.argv[1:]).strip() or None  # e.g. "Microphone Array"
    transcriber = Transcriber()

    print("Loading the speech model (the first run downloads about 150 MB)...")
    start = time.perf_counter()
    try:
        transcriber.load()
    except TranscriptionError as exc:
        print(exc)
        return 1
    memory_mb = psutil.Process().memory_info().rss / 1_000_000
    print(f"Model ready in {time.perf_counter() - start:.1f} s. NOVA is using {memory_mb:.0f} MB of RAM.")

    try:
        recorder = Recorder(find_input_device(name))
        print(f"Speak now for {SECONDS} seconds...")
        recorder.start()
        time.sleep(SECONDS)
        audio = recorder.stop()
    except (ValueError, sd.PortAudioError) as exc:
        print(f"Microphone problem: {exc}")
        return 1

    start = time.perf_counter()
    try:
        text = transcriber.transcribe(audio)
    except TranscriptionError as exc:
        print(exc)
        return 1
    print(f"Transcribed in {time.perf_counter() - start:.1f} s.")
    print(f'I heard: "{text}"' if text else "I didn't hear any speech.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())