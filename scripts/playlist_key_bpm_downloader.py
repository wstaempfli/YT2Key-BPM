#!/usr/bin/env python3
"""Download a YouTube URL and suffix files with detected key/BPM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from downloader_core import JobConfig, run_job

def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    default_output = root / "downloads"
    default_keyfinder = root / "tools" / "keyfinder_cli" / "build" / "keyfinder_cli"

    parser = argparse.ArgumentParser(description="Download tracks and append [KEY-BPM] to filenames.")
    parser.add_argument("url", help="YouTube playlist URL or song URL")
    parser.add_argument(
        "--mode",
        choices=("playlist", "single"),
        default="playlist",
        help="Download mode: playlist or single song",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="For playlist mode, download only first X tracks",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output,
        help="Directory where audio files are saved",
    )
    parser.add_argument(
        "--audio-format",
        default="mp3",
        help="Output audio format used by yt-dlp (default: mp3)",
    )
    parser.add_argument(
        "--keyfinder-cli",
        type=Path,
        default=default_keyfinder,
        help="Path to compiled keyfinder helper executable",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary WAV files used for key analysis",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = JobConfig(
        url=args.url,
        mode=args.mode,
        output_dir=args.output_dir,
        audio_format=args.audio_format,
        keyfinder_cli=args.keyfinder_cli,
        keep_temp=args.keep_temp,
        limit=args.limit,
    )
    result = run_job(config)
    print(json.dumps(result["items"], indent=2))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
