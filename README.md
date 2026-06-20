# Auralis

**Listen. Transcribe. Study.**

A Windows desktop app for transcribing university lectures (Hebrew + English) locally on your machine. Captures system audio from Zoom, Teams, or any other source via WASAPI loopback, transcribes live with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) using the [Ivrit.AI](https://ivrit.ai) Hebrew fine-tune, and produces a higher-quality post-processed transcript after each session.

Everything runs locally. Nothing leaves your machine.

## Features

- **Live transcription** with a Hebrew-tuned Whisper model.
- **High-quality post-processing pass** on the saved audio after Stop.
- **Course + Category organization** (e.g. `Optoelectronics → Lectures`).
- **Library** tab to browse, re-process, move, and delete past recordings.
- **Trigger keywords** — when the lecturer says one of your trigger words, the recent transcript context is copied to your clipboard for instant paste into Claude/Cowork.
- **Dynamic vocabulary** — recurring words from the lecture get auto-fed back into Whisper's prompt every 10 minutes.
- **Three audio capture modes** — whole-system audio, a specific output device, or a single app (Zoom, Chrome, etc.) via WASAPI Process Loopback. The per-app picker live-refreshes to show whatever's currently producing audio.
- **Bundled Hebrew model** — Ivrit.AI v3 turbo ships inside the installer. Fully offline from first launch; no Hugging Face downloads needed.
- **Pixel-perfect Claude Design UI** rendered in Chrome/Edge app-mode (Eel). Dark + light themes, soft cards, custom typography.
- **All-local, no API keys required.**

## Install (end users)

### Windows

1. Download the latest `AuralisSetup-x.y.z.exe` from the [Releases page](https://github.com/amitkaradi/auralis/releases).
2. Double-click to install. Wizard takes 30 seconds.
3. Launch from the Start menu.
4. First run shows a short onboarding (audio device + first course).
5. First recording downloads the Whisper model (~1.5 GB) — one-time, cached forever. The "full" installer ships the Hebrew model inside and is fully offline from launch.

### macOS

1. Download the latest `AuralisSetup-x.y.z.dmg` from the [Releases page](https://github.com/amitkaradi/auralis/releases).
2. Double-click the `.dmg`, drag **Auralis** into Applications.
3. First launch: macOS will warn about an unsigned app — right-click → Open → Open Anyway.
4. To capture **system audio** on macOS you need a virtual audio device — install [**BlackHole 2ch**](https://existential.audio/blackhole/) (free), set it as your Mac's audio output, and Auralis will pick it up.
5. The per-app capture mode (Specific app) is **Windows-only** for now — Mac users see only "Whole system audio".

## Install (from source — developers)

### Windows

1. Install **Python 3.12+** from https://www.python.org/downloads/windows/ (tick *"Add python.exe to PATH"*).
2. Install **Google Chrome** or **Microsoft Edge** (used for the app window via [Eel](https://github.com/python-eel/Eel)). One is almost certainly already on Windows 11.
3. Clone the repo to a short path, e.g. `C:\Auralis`.
4. Double-click `setup_and_run.bat`. First run creates `.venv`, installs deps (~2 minutes) and launches the app.

```
git clone https://github.com/amitkaradi/auralis.git C:\Auralis
cd C:\Auralis
setup_and_run.bat
```

### macOS

```sh
git clone https://github.com/amitkaradi/auralis.git ~/Auralis
cd ~/Auralis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-mac.txt
python auralis.py
```

Building a local `.dmg` (instead of letting CI do it):
```sh
pip install pyinstaller
pyinstaller --noconfirm --clean auralis-mac.spec
brew install create-dmg
create-dmg --volname "Auralis" --window-pos 200 120 --window-size 600 380 \
  --icon-size 100 --app-drop-link 450 190 \
  dist/Auralis.dmg dist/Auralis.app
```

GitHub Actions auto-builds the `.dmg` for every `v*` tag — see `.github/workflows/build-mac.yml`.

## Architecture

The UI is HTML/CSS/JSX (rendered as React in Chrome/Edge app-mode via Eel); the Python backend handles audio capture, transcription, post-processing, and persistence. JS↔Python over a local WebSocket.

```
ui/index.html              HTML entry — loads React + Babel locally
ui/auralis.css             Design tokens (dark + light palettes)
ui/app.jsx                 App root: routing, modals, mini player, push handlers
ui/auralis-shell.jsx       Sidebar + topbar + icons (Ico, AuFrame, AuTopbar)
ui/auralis-live.jsx        Live tab: idle / recording / polishing
ui/auralis-library.jsx     Library tab: course rail + recording rows
ui/auralis-settings.jsx    Settings tab: sectioned nav + controls
auralis.py                 Backend: AudioCaptureThread, TranscriptionThread,
                           PostProcessThread, TriggerHandler, AppConfig +
                           @eel.expose'd API methods
```

## Build an installer (developers)

Requires:
- Working `.venv` (run `setup_and_run.bat` once first).
- [Inno Setup 6](https://jrsoftware.org/isdl.php) installed (free, one-click).

Then:
```
build_release.bat
```

Output: `dist\AuralisSetup-1.1.1.exe` — a single double-click installer to distribute via GitHub Releases or your own site.

## File layout

| Path                                       | Contents                              |
|--------------------------------------------|---------------------------------------|
| `auralis.py`                               | Python backend + Eel bridge           |
| `ui/`                                      | HTML/CSS/JSX from Claude Design (the actual UI) |
| `ui/vendor/`                               | Local copies of React + Babel (offline) |
| `requirements.txt`                         | Pip dependencies                      |
| `setup_and_run.bat`                        | First-run setup + launcher            |
| `build_icons.py`                           | Generates `assets/auralis.ico` + tiles |
| `auralis.spec`                             | PyInstaller config                    |
| `auralis.iss`                              | Inno Setup config                     |
| `version_info.txt`                         | Windows EXE version metadata          |
| `build_release.bat`                        | One-click build: icons → exe → installer |
| `assets/`                                  | Icons (generated by `build_icons.py`) |
| `LICENSE.txt`                              | MIT license + 3rd-party attributions  |

## User data at runtime

| Path                                                       | What                            |
|------------------------------------------------------------|---------------------------------|
| `recordings/<course>/<category>/lecture_<ts>.wav`          | Raw WAV recordings (16 kHz mono)|
| `live_transcripts/<course>/<category>/transcript_<ts>.txt` | Live transcripts saved on Stop  |
| `post_processed_transcripts/<course>/<category>/...`       | High-quality post-pass output   |
| `triggers/latest.txt` + `triggers/trigger_<ts>_*.txt`      | Trigger payloads                |
| `logs/auralis.log`                                         | Rotating log file               |
| `config.json`                                              | User settings                   |

## Privacy

Auralis processes all audio **locally**. No audio, transcript, or trigger payload is uploaded anywhere. The only network access is the one-time Whisper model download from Hugging Face on first launch. You can disable your network adapter after that and the app keeps working.

## License

MIT. See `LICENSE.txt`. Bundles third-party components under their own licenses (Whisper, ctranslate2, soundcard, React, Eel, etc.).

## Credits

- Speech recognition: [OpenAI Whisper](https://github.com/openai/whisper) via [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- Hebrew accuracy: [Ivrit.AI](https://ivrit.ai) fine-tunes
- Audio loopback: [python-soundcard](https://github.com/bastibe/SoundCard)
- App window + JS bridge: [Eel](https://github.com/python-eel/Eel)
- UI framework: [React 18](https://react.dev) (in-browser Babel transform)
- Visual design: produced with [Claude Design](https://claude.ai/design)
- Typography: [Inter](https://rsms.me/inter), [Heebo](https://fonts.google.com/specimen/Heebo), [JetBrains Mono](https://www.jetbrains.com/lp/mono/)
