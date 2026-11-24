# NOVA: a free, local voice assistant for Windows

NOVA is a hands-free desktop assistant that runs on your own computer. Say "Hey Jarvis" (a stand-in until a custom "Hey Nova" model is trained) and tell it what to do: open apps, open websites in a chosen Chrome profile, search Google or YouTube, change the volume, take screenshots, and switch, minimize, maximize or close windows.

Everything runs locally and costs nothing: no paid APIs, no cloud AI, no accounts.

![NOVA web interface](docs/images/nova-ui.png)

## What you can say

| Say | NOVA does |
|---|---|
| "Hey Jarvis, open Discord" | Opens the app and checks that it is running |
| "Open GitHub on AG" | Opens the site in the Chrome profile you call "AG" |
| "Search YouTube for programming tutorials" | Opens the search results in Chrome |
| "Turn the volume down", "set the volume to 30", "mute" | Changes the volume and reads it back to confirm |
| "Take a screenshot" | Saves it in `Pictures\NOVA Screenshots` |
| "Switch to Spotify", "minimize Chrome", "close Spotify" | Controls the app's windows and checks the result |
| "Hey Jarvis" ... "Yes?" ... "Open Spotify" | Works with a pause between the wake word and the command |

NOVA answers out loud, and it only says an action worked after verifying it.

## How it works

```
Microphone -> wake word (openWakeWord) -> speech to text (faster-whisper)
   -> command parser -> allowlist check -> tools (apps, Chrome, volume, windows)
   -> result verification -> spoken reply + web page status
```

- **Wake word:** openWakeWord runs on the CPU and uses about 6 to 7 percent of one core while listening.
- **Speech to text:** faster-whisper with the `base.en` model, CPU only.
- **Commands:** a deterministic parser, not an AI model. Your words are never run as code. They only choose between a few approved actions.
- **Interface:** a small FastAPI server and a plain HTML page showing the state (waiting, listening, transcribing, executing, speaking), a mute button and a conversation log.

## Privacy and safety

- Wake-word detection and speech recognition run on your machine. Audio is not saved or sent anywhere.
- The first run downloads the speech and wake-word models, so it needs internet once.
- The server only accepts requests from `127.0.0.1`, and actions need a custom header, so other websites can't press its buttons.
- NOVA only controls apps and sites listed in `nova.toml`, and only opens `https` sites.
- NOVA refuses to close the program it is running inside.
- The microphone is on while hands-free mode is on. Windows shows its microphone icon, and the mute button on the page turns it off.

## Requirements

- Windows 11
- Python 3.11 (3.12 should also work; I have not tested it)
- A microphone
- Chrome, plus whichever desktop apps you want to control

## Setup

```powershell
git clone https://github.com/PjBalcruz/nova-desktop-assistant.git
cd nova-desktop-assistant
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

If PowerShell refuses to activate the environment, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

### Configure `nova.toml`

- **Apps:** `start_name` must match the name shown by `Get-StartApps` in PowerShell.
- **Chrome profiles:** map your spoken names to Chrome's profile folders. List them with:

```powershell
$s = Get-Content "$env:LOCALAPPDATA\Google\Chrome\User Data\Local State" -Raw | ConvertFrom-Json
$s.profile.info_cache.PSObject.Properties | ForEach-Object { "$($_.Name) = $($_.Value.name)" }
```

- **Microphone:** `input_device` is part of your microphone's name. List the devices with:

```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```

## Run

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The first run downloads about 150 MB of models. When the page says "Speech model ready", hands-free mode starts by itself and NOVA says "Hands-free mode is on."

### Run quietly in the background

```powershell
cd backend
..\.venv\Scripts\pythonw.exe run_nova.py
```

Messages go to `logs\nova.log`. To start NOVA when you log in, put a shortcut to `pythonw.exe run_nova.py` (with `backend` as the working folder) in `shell:startup`.

To stop it:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*run_nova.py*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

### Try commands without a microphone

```powershell
cd backend
python -m app.cli "open spotify"
```

## Tests

```powershell
cd backend
python -m pytest
```

The tests cover the command parser. Opening apps and controlling windows were tested by hand on one machine (Windows 11, Intel Core i7, 16 GB RAM).

## Project layout

```
nova.toml                   apps, sites, Chrome profiles, search engines, microphone
backend/
  run_nova.py               background launcher with a log file
  app/
    main.py                 local API and web page
    assistant.py            state machine used by the page
    hands_free.py           wake word -> command -> reply loop
    parser.py               sentence -> structured command
    orchestrator.py         picks the tool for each command
    automation/             apps, Chrome, volume and screenshots, windows
    voice/                  microphone, wake word, speech to text, text to speech
    static/index.html       the web page
  tests/
FEATURE_BACKLOG.md          what is done and what is planned
```

## Known limits

- Windows only, English only, tested on one machine.
- The wake phrase is "Hey Jarvis" for now. A custom "Hey Nova" model still has to be trained.
- Short names such as "AG" are sometimes misheard, so `nova.toml` lists common mishearings as aliases.
- NOVA does not hold a conversation yet: no follow-up questions and no interrupting it while it speaks.
- Messenger's desktop app was retired in December 2025, so NOVA opens messenger.com in Chrome.
- Notification reading (email, Messenger, LinkedIn) is not built. See the backlog.

## Roadmap

See [FEATURE_BACKLOG.md](FEATURE_BACKLOG.md). Next: a custom "Hey Nova" wake word, a "which account?" follow-up question, and research into reading Windows notifications.