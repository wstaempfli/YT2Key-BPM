# FL Studio VST3 + Companion Service

This project includes a macOS VST3 plugin UI and a Python companion service that performs YouTube download and key/BPM tagging in the background.

## Components

- VST3 plugin source: `plugin/`
- Companion API service: `service/app.py`
- Reusable downloader/key/BPM core: `scripts/downloader_core.py`

## Prerequisites

- macOS
- FL Studio with VST3 support
- Python 3.10+
- `ffmpeg` available in PATH
- JUCE source checkout for plugin build
- CMake + C++ compiler

## Setup

1. Build keyfinder helper:

```bash
./scripts/build_keyfinder_cli.sh
```

2. Create companion environment:

```bash
./scripts/setup_companion.sh
```

3. Start companion service:

```bash
./scripts/run_companion.sh
```

Service URL: `http://127.0.0.1:8765`  
Health check: `GET /health`

You can override host/port:

```bash
COMPANION_HOST=127.0.0.1 COMPANION_PORT=8765 ./scripts/run_companion.sh
```

## Build VST3

```bash
./scripts/build_vst3.sh /absolute/path/to/JUCE
```

Resulting plugin bundle will be in `plugin/build`.

## Install VST3 in FL Studio (macOS)

Copy `.vst3` bundle to:

```bash
~/Library/Audio/Plug-Ins/VST3
```

Then in FL Studio:

1. Open Plugin Manager.
2. Scan for new plugins.
3. Add **FL Beat Downloader** to a channel/effect slot.

## Plugin Workflow

1. Paste playlist/song URL.
2. Choose single-song mode or playlist mode.
3. (Playlist mode) set optional limit.
4. Choose target directory.
5. Click **Start**.
6. Watch progress; use **Cancel** to stop the job.

## FL Studio Test Checklist

Use this exact order for a clean first test:

1. In Terminal, from project root:

```bash
./scripts/build_keyfinder_cli.sh
./scripts/setup_companion.sh
```

2. Export companion root so plugin auto-start can find scripts:

```bash
export FL_VST_COMPANION_ROOT="/absolute/path/to/this/project"
```

3. Start companion service once manually:

```bash
./scripts/run_companion.sh
```

4. In another terminal, build plugin:

```bash
./scripts/build_vst3.sh /absolute/path/to/JUCE
```

5. Copy generated `.vst3` bundle into:

```bash
~/Library/Audio/Plug-Ins/VST3
```

6. Open FL Studio -> Plugin Manager -> **Find installed plugins**.
7. Add **FL Beat Downloader** to a channel or effect slot.
8. In plugin UI:
   - Paste URL
   - Set mode (`single` for one song or playlist with limit)
   - Choose target directory
   - Click **Start**
9. Confirm:
   - status line shows `Service: online`
   - progress moves
   - logs update in the plugin panel
10. Verify output filenames include suffixes like `[Cm-134]`.

If scan/load fails:
- Verify FL Studio is scanning `~/Library/Audio/Plug-Ins/VST3`.
- Remove old cached plugin entries and rescan.
- Rebuild plugin after any code changes.

## API Endpoints

- `GET /health`
- `GET /jobs?limit=20`
- `POST /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/cancel`

Request body for `POST /jobs`:

```json
{
  "url": "https://www.youtube.com/playlist?list=...",
  "mode": "playlist",
  "limit": 5,
  "target_dir": "/Users/name/Music/Beats",
  "audio_format": "mp3",
  "keep_temp": false
}
```

## Notes

- Heavy download/analysis runs in the companion process, not in FL Studio's plugin process.
- The VST3 UI polls the companion service for progress updates.
- If the service is unavailable, the plugin tries to launch `scripts/run_companion.sh`.
- For reliable auto-launch inside FL Studio, set `FL_VST_COMPANION_ROOT` to this project root before launching FL Studio.
