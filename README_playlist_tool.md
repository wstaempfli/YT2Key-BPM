# YouTube Playlist Key/BPM Suffix Tool

This tool downloads tracks from a YouTube playlist, detects key and BPM for each file, and renames each file to include a suffix like `[Cm-140]`.

## What gets installed

- Python downloader/orchestrator: `scripts/playlist_key_bpm_downloader.py`
- libKeyFinder helper binary source: `tools/keyfinder_cli/`
- Build helper script: `scripts/build_keyfinder_cli.sh`

## Prerequisites

- Python 3.10+
- `ffmpeg` in PATH
- `yt-dlp` in PATH (also included in `requirements.txt`)
- CMake + C++ toolchain
- FFTW library (required by libKeyFinder)

On macOS with Homebrew:

```bash
brew install ffmpeg fftw cmake
```

## Setup

1. Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Build the keyfinder helper binary:

```bash
./scripts/build_keyfinder_cli.sh
```

Binary output:

```bash
tools/keyfinder_cli/build/keyfinder_cli
```

## Usage

Download full playlist:

```bash
python3 scripts/playlist_key_bpm_downloader.py "https://www.youtube.com/playlist?list=YOUR_LIST_ID"
```

Download only first 5 tracks:

```bash
python3 scripts/playlist_key_bpm_downloader.py "https://www.youtube.com/playlist?list=YOUR_LIST_ID" --limit 5
```

Custom output folder and format:

```bash
python3 scripts/playlist_key_bpm_downloader.py "https://www.youtube.com/playlist?list=YOUR_LIST_ID" --output-dir "./my_beats" --audio-format mp3
```

## Filename behavior

- Output template starts as: `001 - Track Name.mp3`
- After analysis: `001 - Track Name [Cm-140].mp3`
- If a filename already exists, the tool appends `(1)`, `(2)`, etc.
- If analysis fails on key or BPM, `UNK` is used for that part.

## Notes

- Key detection is done by `libKeyFinder` through `keyfinder_cli`.
- BPM detection is done in Python using `librosa`.
- The script converts files to temporary mono WAV for key detection.
- Use `--keep-temp` if you want those `.analysis.wav` files preserved.

## Troubleshooting

- `Missing required executable: yt-dlp` or `ffmpeg`:
  - Ensure both commands are available in your shell PATH.
- CMake cannot find FFTW:
  - Install FFTW (`brew install fftw`) and rerun build script.
- Keyfinder binary not found:
  - Rebuild with `./scripts/build_keyfinder_cli.sh` or pass `--keyfinder-cli /custom/path/keyfinder_cli`.
