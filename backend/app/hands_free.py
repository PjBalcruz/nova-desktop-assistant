"""Hands-free NOVA: wake word -> command -> spoken reply -> back to sleep.

The web page uses this through assistant.py. You can also run it in the terminal:
    python -m app.hands_free hey_jarvis
"""
from __future__ import annotations

import queue
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd

from app.config import NovaConfig, load_config
from app.orchestrator import handle_text
from app.voice.listener import SAMPLE_RATE, find_input_device
from app.voice.speech_to_text import Transcriber, TranscriptionError
from app.voice.text_to_speech import Speaker
from app.voice.wake_word import FRAME_SAMPLES, WakeWordDetector, WakeWordError

FRAME_S = FRAME_SAMPLES / SAMPLE_RATE  # 0.08 s per frame
MIN_SPEECH_S = 0.4  # less speech than this is just the tail of the wake phrase
_CANCEL = re.compile(r"(stop|cancel( that)?|never ?mind)\W*", re.IGNORECASE)


class Stopped(Exception):
    """Hands-free mode was switched off."""


def rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))


class Frames:
    """80 ms microphone frames, filled by the audio callback."""

    def __init__(self, stop: threading.Event) -> None:
        self._q: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._stop = stop

    def callback(self, indata, frame_count, time_info, status) -> None:
        try:
            self._q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass  # drop audio rather than fall behind

    def get(self, timeout: float = 2.0) -> np.ndarray:
        waited = 0.0
        while True:
            if self._stop.is_set():
                raise Stopped
            try:
                return self._q.get(timeout=0.2)
            except queue.Empty:
                waited += 0.2
                if waited >= timeout:
                    raise sd.PortAudioError("The microphone stopped sending audio.") from None

    def flush(self) -> None:
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return


def capture(frames: Frames, threshold: float, wait_s: float, max_s: float = 10.0,
            end_silence_s: float = 0.9) -> tuple[np.ndarray | None, float]:
    """Record until the user stops talking. Returns (audio, seconds of speech); audio is
    None if nobody started talking within wait_s seconds."""
    pre: deque[np.ndarray] = deque(maxlen=3)  # keeps the start of the first word
    chunks: list[np.ndarray] = []
    started, waited, speech_frames, silent_run = False, 0.0, 0, 0
    while True:
        frame = frames.get()
        loud = rms(frame) >= threshold
        if not started:
            pre.append(frame)
            waited += FRAME_S
            if not loud:
                if waited >= wait_s:
                    return None, 0.0
                continue
            started = True
            chunks.extend(pre)
            speech_frames = 1
        else:
            chunks.append(frame)
            if loud:
                speech_frames += 1
                silent_run = 0
            else:
                silent_run += 1
        if silent_run * FRAME_S >= end_silence_s or len(chunks) * FRAME_S >= max_s:
            break
    audio = np.concatenate(chunks).astype(np.float32) / 32768.0  # Whisper wants -1..1 floats
    return audio, speech_frames * FRAME_S


class HandsFree:
    def __init__(
        self,
        config: NovaConfig,
        transcriber: Transcriber,
        speaker: Speaker,
        wake_model: str,
        stop: threading.Event,
        on_state: Callable[[str, str], None] | None = None,
        on_log: Callable[[str, str], None] | None = None,
    ) -> None:
        self.config = config
        self.transcriber = transcriber
        self.speaker = speaker
        self.stop = stop
        self.cancel = threading.Event()  # set by the Cancel button
        self.frames = Frames(stop)
        self.detector = WakeWordDetector(wake_model)  # may raise WakeWordError
        self.threshold = 120.0
        self._speech_end = time.perf_counter()
        self._state_fn = on_state or (lambda state, detail: print(f"[{detail}]"))
        self._log_fn = on_log or (lambda role, text: print(f"{'You' if role == 'user' else 'NOVA'}: {text}"))

        stem = Path(wake_model).stem
        self.wake_name = stem.replace("_", " ").title()  # "Hey Jarvis"
        # Words to drop from the start of what Whisper heard, e.g. "Hey Jarvis," or "Hey Nova,".
        names = {"nova", stem.split("_")[-1].lower()}
        self._wake_prefix = re.compile(
            r"^\W*(?:(?:hey|hi|okay|ok)\W+)?(?:" + "|".join(re.escape(n) for n in names) + r")\b\W*",
            re.IGNORECASE,
        )

    def say(self, text: str) -> None:
        self._log_fn("nova", text)
        self._state_fn("speaking", "Speaking...")
        self.speaker.speak(text)  # blocks until finished; meanwhile mic audio piles up unused
        self.frames.flush()  # ...and is thrown away, so NOVA never hears itself
        time.sleep(0.3)
        self.frames.flush()

    def calibrate(self) -> None:
        self._state_fn("starting", "Measuring room noise. Please stay quiet for a second...")
        levels = [rms(self.frames.get()) for _ in range(15)]
        noise = float(np.median(levels[5:]))  # skip the first frames while the stream starts
        self.threshold = max(noise * 4, 120.0)
        print(f"Room noise level {noise:.0f}, speech threshold {self.threshold:.0f}.")

    def hear(self, audio: np.ndarray) -> str:
        """Transcribe, drop the wake word, return '' if nothing useful was said."""
        self._state_fn("transcribing", "Turning your voice into text...")
        self._speech_end = time.perf_counter()
        try:
            raw = self.transcriber.transcribe(audio)
        except TranscriptionError as exc:
            print(exc)
            return ""
        print(f'Heard: "{raw}"')
        text = self._wake_prefix.sub("", raw).strip()
        return text if re.search(r"\w", text) else ""

    def wait_for_wake(self) -> None:
        self._state_fn("sleeping", f'Say "{self.wake_name}"')
        self.frames.flush()
        self.detector.reset()  # forget the old "Hey ..." so it can't trigger a second time
        while True:
            score = self.detector.process(self.frames.get())
            if self.detector.is_triggered(score):
                print(f"Wake word heard! (score {score:.2f})")
                return

    def conversation(self) -> None:
        self.cancel.clear()
        self._state_fn("listening", "Listening... go ahead.")
        # The command may follow the wake word in the same breath ("Hey Jarvis, open Discord").
        text = ""
        audio, spoken = capture(self.frames, self.threshold, wait_s=0.9)
        if audio is not None and spoken >= MIN_SPEECH_S:
            text = self.hear(audio)
        if not text:
            self.say("Yes?")
            self._state_fn("listening", "Listening... go ahead.")
            audio, _ = capture(self.frames, self.threshold, wait_s=6.0)
            if audio is None:
                self.say("I didn't hear anything.")
                return
            text = self.hear(audio)
            if not text:
                self.say("I didn't catch that.")
                return
        if self.cancel.is_set() or _CANCEL.fullmatch(text):
            self.say("Okay.")
            return
        self._log_fn("user", text)
        self._state_fn("executing", "Working on it...")
        try:
            message = handle_text(text, self.config).message
        except Exception as exc:  # never let one bad command kill hands-free mode
            message = f"Something went wrong: {exc}"
        print(f"[{time.perf_counter() - self._speech_end:.1f} s from end of speech to reply]")
        self.say(message)

    def run(self) -> None:
        """Listen until the stop event is set. The microphone is only open inside this method."""
        self.speaker.warm_up()
        device = find_input_device(self.config.input_device)
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=FRAME_SAMPLES, device=device, callback=self.frames.callback):
                self.calibrate()
                self.say("Hands-free mode is on.")
                while True:
                    self.wait_for_wake()
                    self.conversation()
        except Stopped:
            return


def main() -> int:
    config = load_config()
    model = sys.argv[1] if len(sys.argv) > 1 else config.wake_word
    stop = threading.Event()
    transcriber, speaker = Transcriber(), Speaker()
    print("Loading the speech model...")
    try:
        transcriber.load()
        app = HandsFree(config, transcriber, speaker, model, stop)
        app.run()
    except (WakeWordError, TranscriptionError, ValueError) as exc:
        print(exc)
        return 1
    except sd.PortAudioError as exc:
        print(f"Microphone problem: {exc}")
        return 1
    except KeyboardInterrupt:
        stop.set()
        speaker.stop()
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())