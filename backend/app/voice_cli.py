"""Terminal push-to-talk: mic -> text -> action -> spoken reply."""
from __future__ import annotations

import sys

import sounddevice as sd

from app.config import load_config
from app.orchestrator import handle_text
from app.voice.listener import Recorder, find_input_device
from app.voice.speech_to_text import Transcriber, TranscriptionError
from app.voice.text_to_speech import Speaker


def main() -> int:
    config = load_config()
    mic_name = " ".join(sys.argv[1:]).strip() or None  # e.g. "Microphone Array"
    transcriber = Transcriber()
    speaker = Speaker()

    print("Loading the speech model...")
    try:
        transcriber.load()
        recorder = Recorder(find_input_device(mic_name))
    except (TranscriptionError, ValueError) as exc:
        print(exc)
        return 1
    print("Ready. Press Enter to start talking, press Enter again to stop. Type q then Enter to quit.")

    try:
        while True:
            if input("> ").strip().lower() == "q":
                return 0
            try:
                recorder.start()
            except sd.PortAudioError as exc:
                print(f"Microphone problem: {exc}")
                continue
            print("Listening... press Enter when you're done.")
            input()
            audio = recorder.stop()

            print("Transcribing...")
            try:
                text = transcriber.transcribe(audio)
            except TranscriptionError as exc:
                print(exc)
                speaker.speak("Sorry, speech recognition failed.")
                continue
            if not text:
                print("I didn't hear any speech.")
                speaker.speak("I didn't catch that.")
                continue

            print(f'You said: "{text}"')
            result = handle_text(text, config)
            print(result.message)
            speaker.speak(result.message)
    except (KeyboardInterrupt, EOFError):
        recorder.stop()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())