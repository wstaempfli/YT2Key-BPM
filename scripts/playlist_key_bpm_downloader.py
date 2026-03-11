#!/usr/bin/env python3
"""Download a YouTube playlist and suffix files with detected key/BPM."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    default_output = root / "downloads"
    default_keyfinder = root / "tools" / "keyfinder_cli" / "build" / "keyfinder_cli"

    parser = argparse.ArgumentParser(
        description="Download a YouTube playlist and append [KEY-BPM] to filenames.",
    )
    parser.add_argument("playlist_url", help="YouTube playlist URL")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Download only first X tracks of the playlist",
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


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def ensure_dependencies() -> list[str]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("Missing required executable: ffmpeg")

    if shutil.which("yt-dlp"):
        return ["yt-dlp"]

    yt_dlp_module = run_command([sys.executable, "-m", "yt_dlp", "--version"])
    if yt_dlp_module.returncode == 0:
        return [sys.executable, "-m", "yt_dlp"]

    raise RuntimeError(
        "Missing yt-dlp. Install it in PATH or in the current Python environment.",
    )


def download_playlist(
    yt_dlp_cmd: list[str],
    playlist_url: str,
    output_dir: Path,
    audio_format: str,
    limit: int | None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(output_dir / "%(playlist_index)03d - %(title)s.%(ext)s")
    cmd = [
        *yt_dlp_cmd,
        "--yes-playlist",
        "--extract-audio",
        "--audio-format",
        audio_format,
        "--output",
        outtmpl,
        "--print",
        "after_move:%(filepath)s",
        playlist_url,
    ]
    if limit:
        cmd.extend(["--playlist-end", str(limit)])

    result = run_command(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed:\n{result.stderr.strip() or result.stdout.strip()}")

    downloaded: list[Path] = []
    for line in result.stdout.splitlines():
        if not line.startswith("after_move:"):
            continue
        path_str = line.split("after_move:", 1)[1].strip()
        if path_str:
            p = Path(path_str)
            if p.exists():
                downloaded.append(p)

    # Fallback in case yt-dlp output parsing changes.
    if not downloaded:
        downloaded = sorted(
            [p for p in output_dir.iterdir() if p.is_file()],
            key=lambda p: p.name,
        )
        if limit is not None:
            downloaded = downloaded[:limit]

    return downloaded


def sanitize_for_filename(text: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]+", "_", text).strip()


def unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def convert_to_analysis_wav(audio_file: Path, keep_temp: bool) -> tuple[Path, bool]:
    wav_path = audio_file.with_suffix(".analysis.wav")
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_file),
        "-ac",
        "1",
        "-ar",
        "44100",
        str(wav_path),
    ]
    result = run_command(ffmpeg_cmd)
    if result.returncode != 0 or not wav_path.exists():
        raise RuntimeError(f"ffmpeg conversion failed for {audio_file.name}: {result.stderr.strip()}")
    return wav_path, (not keep_temp)


def detect_key_with_cli(keyfinder_cli: Path, wav_file: Path) -> str:
    if not keyfinder_cli.exists():
        raise RuntimeError(f"keyfinder CLI not found: {keyfinder_cli}")

    result = run_command([str(keyfinder_cli), str(wav_file)])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "key detection failed")
    key = result.stdout.strip()
    if not key:
        raise RuntimeError("keyfinder returned empty key")
    return key


def detect_bpm(audio_file: Path) -> int:
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_file), sr=None, mono=True)
    if y.size == 0:
        raise RuntimeError("audio buffer is empty")

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    if isinstance(tempo, np.ndarray):
        if tempo.size == 0:
            raise RuntimeError("tempo array empty")
        tempo_value = float(tempo[0])
    else:
        tempo_value = float(tempo)
    if not math.isfinite(tempo_value) or tempo_value <= 0:
        raise RuntimeError(f"invalid tempo value: {tempo_value}")
    return int(round(tempo_value))


def iter_audio_files(files: Iterable[Path]) -> Iterable[Path]:
    for p in files:
        if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac"}:
            yield p


def process_file(audio_file: Path, keyfinder_cli: Path, keep_temp: bool) -> dict[str, str]:
    wav_file = None
    remove_wav = False
    key = "UNK"
    bpm = "UNK"
    try:
        wav_file, remove_wav = convert_to_analysis_wav(audio_file, keep_temp)
        key = detect_key_with_cli(keyfinder_cli, wav_file)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] key detection failed for {audio_file.name}: {exc}", file=sys.stderr)
    finally:
        if wav_file and remove_wav and wav_file.exists():
            wav_file.unlink()

    try:
        bpm = str(detect_bpm(audio_file))
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] BPM detection failed for {audio_file.name}: {exc}", file=sys.stderr)

    original_stem = audio_file.stem
    # Avoid repeatedly appending suffix when script is rerun.
    original_stem = re.sub(r"\s+\[[^\]]+\]$", "", original_stem)
    suffix_tag = sanitize_for_filename(f"{key}-{bpm}")
    renamed = unique_path(audio_file.with_name(f"{original_stem} [{suffix_tag}]{audio_file.suffix}"))
    audio_file.rename(renamed)
    return {"input": audio_file.name, "output": renamed.name, "key": key, "bpm": bpm}


def main() -> int:
    args = parse_args()
    yt_dlp_cmd = ensure_dependencies()

    files = download_playlist(
        yt_dlp_cmd=yt_dlp_cmd,
        playlist_url=args.playlist_url,
        output_dir=args.output_dir,
        audio_format=args.audio_format,
        limit=args.limit,
    )
    audio_files = list(iter_audio_files(files))
    if not audio_files:
        print("No audio files were downloaded.", file=sys.stderr)
        return 1

    report: list[dict[str, str]] = []
    for audio_file in audio_files:
        report.append(process_file(audio_file, args.keyfinder_cli, args.keep_temp))

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
