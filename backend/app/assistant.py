"""Coordinates microphone, speech recognition, commands and spoken replies."""
from __future__ import annotations

import threading
from pathlib import Path

import sounddevice as sd

from app.config import NovaConfig
from app.hands_free import HandsFree
from app.orchestrator import handle_text
from app.voice.listener import Recorder, find_input_device
from app.voice.speech_to_text import Transcriber, TranscriptionError
from app.voice.text_to_speech import Speaker
from app.voice.wake_word import WakeWordError

_MAX_LOG = 50


class AssistantError(Exception):
    """A problem the user should see (for example: NOVA is busy)."""


class Assistant:
    # states: idle, starting, sleeping, listening, transcribing, executing, speaking
    def __init__(self, config: NovaConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._state = "idle"
        self._detail = "Ready"
        self._voice_status = "loading"  # loading, ready or unavailable
        self._voice_message = ""
        self._log: list[dict[str, str]] = []
        self._cancel = threading.Event()
        self._transcriber = Transcriber()
        self._speaker = Speaker()
        self._recorder: Recorder | None = None
        # hands-free mode
        self._hands_free = False
        self._hf: HandsFree | None = None
        self._hf_stop: threading.Event | None = None
        self._hf_thread: threading.Thread | None = None
        self._wake_name = Path(config.wake_word).stem.replace("_", " ").title()
        threading.Thread(target=self._load_voice, daemon=True).start()

    # ---------- status ----------
    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "detail": self._detail,
                "voice": self._voice_status,
                "voice_message": self._voice_message,
                "hands_free": self._hands_free,
                "wake_name": self._wake_name,
                "mic_on": self._hands_free or self._state == "listening",
                "log": list(self._log),
            }

    def _set(self, state: str, detail: str) -> None:
        with self._lock:
            self._state, self._detail = state, detail

    def _add(self, role: str, text: str) -> None:
        with self._lock:
            self._log.append({"role": role, "text": text})
            del self._log[:-_MAX_LOG]

    def _load_voice(self) -> None:
        try:
            self._transcriber.load()
        except TranscriptionError as exc:
            with self._lock:
                self._voice_status, self._voice_message = "unavailable", str(exc)
            return
        with self._lock:
            self._voice_status = "ready"
        if self._config.hands_free_on_start:  # no click needed: start listening right away
            try:
                self.start_hands_free()
            except AssistantError:
                pass

    # ---------- push-to-talk ----------
    def start_listening(self) -> None:
        with self._lock:
            if self._voice_status != "ready":
                raise AssistantError(self._voice_message or "The speech model is still loading.")
            if self._hands_free:
                raise AssistantError("Hands-free is on. Mute it to use the mic button.")
            if self._state != "idle":
                raise AssistantError("NOVA is busy. Press Cancel first.")
            self._cancel.clear()
            try:
                recorder = Recorder(find_input_device(self._config.input_device))
                recorder.start()
            except (ValueError, sd.PortAudioError) as exc:
                raise AssistantError(f"Microphone problem: {exc}") from exc
            self._recorder = recorder
            self._state, self._detail = "listening", "Speak now, then press the button again."

    def stop_listening(self) -> None:
        with self._lock:
            if self._state != "listening" or self._recorder is None:
                raise AssistantError("I'm not listening right now.")
            audio = self._recorder.stop()
            self._recorder = None
            self._state, self._detail = "transcribing", "Turning your voice into text..."
        threading.Thread(target=self._process_audio, args=(audio,), daemon=True).start()

    def _process_audio(self, audio) -> None:
        try:
            text = self._transcriber.transcribe(audio)
        except TranscriptionError as exc:
            self._say(f"Sorry, speech recognition failed. {exc}")
            return
        except Exception as exc:  # never leave the page stuck
            self._say(f"Something went wrong: {exc}")
            return
        if self._cancel.is_set():
            self._set("idle", "Cancelled")
            return
        if not text:
            self._say("I didn't catch that.")
            return
        self._add("user", text)
        self._run_command(text)

    # ---------- hands-free ----------
    def start_hands_free(self) -> None:
        with self._lock:
            if self._voice_status != "ready":
                raise AssistantError(self._voice_message or "The speech model is still loading.")
            if self._hands_free:
                return
            if self._state != "idle":
                raise AssistantError("NOVA is busy. Press Cancel first.")
            stop = threading.Event()
            thread = threading.Thread(target=self._run_hands_free, args=(stop,), daemon=True)
            self._hf_stop, self._hf_thread = stop, thread
            self._hands_free = True
            self._state, self._detail = "starting", "Starting hands-free mode..."
        thread.start()

    def _run_hands_free(self, stop: threading.Event) -> None:
        try:
            hf = HandsFree(self._config, self._transcriber, self._speaker, self._config.wake_word,
                           stop, on_state=self._set, on_log=self._add)
            with self._lock:
                self._hf = hf
            hf.run()
        except (WakeWordError, ValueError, sd.PortAudioError) as exc:
            if not stop.is_set():
                self._add("nova", f"Hands-free mode stopped: {exc}")
        except Exception as exc:
            self._add("nova", f"Hands-free mode stopped unexpectedly: {exc}")
        finally:
            with self._lock:
                if self._hf_stop is stop:  # only reset if a newer session hasn't taken over
                    self._hf = None
                    self._hf_stop = None
                    self._hands_free = False
                    self._state, self._detail = "idle", "Ready"

    def stop_hands_free(self) -> None:
        with self._lock:
            stop, thread = self._hf_stop, self._hf_thread
        if stop is None:
            return
        stop.set()  # the microphone closes as soon as the loop notices
        self._speaker.stop()
        if thread is not None:
            thread.join(timeout=3)

    # ---------- typed input ----------
    def submit_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            raise AssistantError("Type a command first.")
        with self._lock:
            if self._hands_free:
                raise AssistantError("Hands-free is on. Say a command, or mute it to type.")
            if self._state != "idle":
                raise AssistantError("NOVA is busy. Press Cancel first.")
            self._cancel.clear()
            self._state, self._detail = "executing", "Working on it..."
        self._add("user", text)
        threading.Thread(target=self._run_command, args=(text,), daemon=True).start()

    # ---------- shared ----------
    def _run_command(self, text: str) -> None:
        self._set("executing", "Working on it...")
        try:
            message = handle_text(text, self._config).message
        except Exception as exc:  # never leave the page stuck
            message = f"Something went wrong: {exc}"
        self._say(message)

    def _say(self, message: str) -> None:
        self._add("nova", message)
        self._set("speaking", "Speaking...")
        self._speaker.speak(message)  # returns when finished or cancelled
        self._set("idle", "Ready")

    def cancel(self) -> None:
        with self._lock:
            if self._hands_free and self._hf is not None:
                if self._state == "speaking":
                    self._speaker.stop()
                elif self._state in ("listening", "transcribing"):
                    self._hf.cancel.set()  # the command is skipped
                    self._detail = "Cancelling..."
                elif self._state == "executing":
                    raise AssistantError("Too late to cancel. That action is already running.")
                return
            if self._state == "listening":
                if self._recorder is not None:
                    self._recorder.stop()
                    self._recorder = None
                self._state, self._detail = "idle", "Cancelled"
            elif self._state == "transcribing":
                self._cancel.set()  # the command is skipped when transcription ends
                self._detail = "Cancelling..."
            elif self._state == "speaking":
                self._speaker.stop()
            elif self._state == "executing":
                raise AssistantError("Too late to cancel. That action is already running.")