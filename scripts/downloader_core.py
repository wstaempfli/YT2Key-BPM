"""Reusable downloader + key/BPM analysis core."""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import sys
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ProgressCallback = Callable[[dict], None]
MAX_ANALYSIS_SECONDS = 10 * 60


@dataclass
class JobConfig:
    url: str
    mode: str  # "playlist" | "single"
    output_dir: Path
    audio_format: str
    keyfinder_cli: Path
    keep_temp: bool = False
    limit: int | None = None


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_yt_dlp_with_proxy_fallback(
    cmd: list[str],
    progress: ProgressCallback | None = None,
) -> subprocess.CompletedProcess[str]:
    result = run_command(cmd)
    stderr = result.stderr or ""
    proxy_failed = (
        result.returncode != 0
        and ("Unable to connect to proxy" in stderr or "Tunnel connection failed" in stderr)
    )
    if not proxy_failed:
        return result

    if progress is not None:
        progress(
            {
                "stage": "downloading",
                "message": "Proxy failed; retrying download without proxy",
            }
        )

    clean_env = dict(os.environ)
    for key in (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
    ):
        clean_env.pop(key, None)
    retry_cmd = [*cmd, "--proxy", ""]
    return run_command(retry_cmd, env=clean_env)


def resolve_executable(name: str, fallbacks: list[str] | None = None) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in (fallbacks or []):
        p = Path(candidate)
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    return None


def ensure_dependencies() -> tuple[list[str], str, str]:
    ffmpeg_bin = resolve_executable(
        "ffmpeg",
        fallbacks=[
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/opt/local/bin/ffmpeg",
        ],
    )
    if ffmpeg_bin is None:
        raise RuntimeError("Missing required executable: ffmpeg")
    ffprobe_bin = resolve_executable(
        "ffprobe",
        fallbacks=[
            "/opt/homebrew/bin/ffprobe",
            "/usr/local/bin/ffprobe",
            "/opt/local/bin/ffprobe",
        ],
    )
    if ffprobe_bin is None:
        raise RuntimeError("Missing required executable: ffprobe")

    if shutil.which("yt-dlp"):
        return ["yt-dlp"], ffmpeg_bin, ffprobe_bin

    yt_dlp_module = run_command([sys.executable, "-m", "yt_dlp", "--version"])
    if yt_dlp_module.returncode == 0:
        return [sys.executable, "-m", "yt_dlp"], ffmpeg_bin, ffprobe_bin

    raise RuntimeError("Missing yt-dlp. Install it in PATH or in the current Python environment.")


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


def fetch_playlist_metadata(
    yt_dlp_cmd: list[str],
    playlist_url: str,
    progress: ProgressCallback | None = None,
) -> list[dict]:
    cmd = [
        *yt_dlp_cmd,
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
        playlist_url,
    ]
    result = run_yt_dlp_with_proxy_fallback(cmd, progress=progress)
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout or "{}")
        entries = payload.get("entries") or []
        return [e for e in entries if isinstance(e, dict)]
    except Exception:  # noqa: BLE001
        return []


def parse_yt_dlp_skipped_errors(stderr_text: str, title_by_id: dict[str, str]) -> list[dict]:
    skipped: list[dict] = []
    for line in (stderr_text or "").splitlines():
        match = re.match(r"^ERROR:\s+\[youtube\]\s+([A-Za-z0-9_-]+):\s+(.+)$", line.strip())
        if not match:
            continue
        video_id, reason = match.groups()
        title = title_by_id.get(video_id, video_id)
        skipped.append(
            {
                "input": title,
                "output": title,
                "key": "SKIPPED",
                "bpm": "SKIPPED",
                "key_error": "",
                "bpm_error": "",
                "skipped": True,
                "skip_reason": "yt_dlp_error",
                "skip_detail": reason,
                "video_id": video_id,
            }
        )
    return skipped


def download_audio(
    yt_dlp_cmd: list[str],
    config: JobConfig,
    ffmpeg_location: str,
    progress: ProgressCallback | None = None,
) -> tuple[list[Path], list[dict]]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(config.output_dir / "%(playlist_index)03d - %(title)s.%(ext)s")
    cmd = [
        *yt_dlp_cmd,
        "--ignore-errors",
        "--no-abort-on-error",
        "--extract-audio",
        "--audio-format",
        config.audio_format,
        "--ffmpeg-location",
        ffmpeg_location,
        "--output",
        outtmpl,
        "--print",
        "after_move:%(filepath)s",
    ]

    used_playlist_items = False
    skipped_items: list[dict] = []
    title_by_id: dict[str, str] = {}
    if config.mode == "playlist":
        cmd.append("--yes-playlist")
        selected_items: list[int] = []
        metadata_entries = fetch_playlist_metadata(yt_dlp_cmd, config.url, progress=progress)
        if metadata_entries:
            capped_entries = metadata_entries[: config.limit] if config.limit else metadata_entries
            for idx, entry in enumerate(capped_entries, start=1):
                video_id = str(entry.get("id") or "")
                title = str(entry.get("title") or f"playlist_item_{idx}")
                if video_id:
                    title_by_id[video_id] = title
                duration = entry.get("duration")
                if duration is None:
                    selected_items.append(idx)
                    continue
                try:
                    duration_s = float(duration)
                except Exception:  # noqa: BLE001
                    selected_items.append(idx)
                    continue
                if duration_s > MAX_ANALYSIS_SECONDS:
                    skipped_item = {
                        "input": title,
                        "output": title,
                        "key": "SKIPPED",
                        "bpm": "SKIPPED",
                        "key_error": "",
                        "bpm_error": "",
                        "skipped": True,
                        "skip_reason": "duration_over_10_minutes",
                        "duration_seconds": int(round(duration_s)),
                        "video_id": video_id,
                    }
                    skipped_items.append(skipped_item)
                    if progress is not None:
                        progress(
                            {
                                "stage": "skipped",
                                "index": idx,
                                "total": len(capped_entries),
                                "file": title,
                                "message": "Skipped pre-download: file longer than 10 minutes",
                            }
                        )
                    continue
                selected_items.append(idx)
            if selected_items:
                cmd.extend(["--playlist-items", ",".join(str(i) for i in selected_items)])
                used_playlist_items = True
        if config.limit and not used_playlist_items:
            cmd.extend(["--playlist-end", str(config.limit)])
    else:
        cmd.append("--no-playlist")

    cmd.append(config.url)

    downloaded: list[Path] = []
    result = run_yt_dlp_with_proxy_fallback(cmd, progress=progress)
    stdout_text = result.stdout or ""
    stderr_text = result.stderr or ""
    for line in stdout_text.splitlines():
        if not line.startswith("after_move:"):
            continue
        p = Path(line.split("after_move:", 1)[1].strip())
        if p.exists():
            downloaded.append(p)

    # yt-dlp can return non-zero when some playlist entries are private/unavailable,
    # even if other items downloaded successfully. Treat that as partial success.
    skipped_from_errors = parse_yt_dlp_skipped_errors(stderr_text, title_by_id)
    if skipped_from_errors and progress is not None:
        for item in skipped_from_errors:
            progress(
                {
                    "stage": "skipped",
                    "file": item.get("input", item.get("video_id", "unknown")),
                    "message": item.get("skip_detail", "Skipped unavailable/private video"),
                }
            )
    skipped_items.extend(skipped_from_errors)

    if result.returncode != 0 and not downloaded and not skipped_items:
        raise RuntimeError(f"yt-dlp failed:\n{stderr_text.strip() or stdout_text.strip()}")
    if result.returncode != 0 and downloaded and progress is not None:
        progress(
            {
                "stage": "downloading",
                "message": "Some playlist entries failed (private/unavailable); continuing with downloaded files",
            }
        )

    if not downloaded:
        downloaded = sorted(
            [p for p in config.output_dir.iterdir() if p.is_file()],
            key=lambda p: p.name,
        )
        if config.mode == "playlist" and config.limit is not None:
            downloaded = downloaded[: config.limit]
        elif config.mode == "single":
            downloaded = downloaded[:1]

    audio_files = [p for p in downloaded if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac"}]
    return audio_files, skipped_items


def convert_to_analysis_wav(audio_file: Path, keep_temp: bool, ffmpeg_bin: str) -> tuple[Path, bool]:
    wav_path = audio_file.with_suffix(".analysis.wav")
    ffmpeg_cmd = [
        ffmpeg_bin,
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
    tempo_value = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
    if not math.isfinite(tempo_value) or tempo_value <= 0:
        raise RuntimeError(f"invalid tempo value: {tempo_value}")
    return int(round(tempo_value))


def get_audio_duration_seconds(audio_file: Path, ffprobe_bin: str) -> float | None:
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(audio_file),
    ]
    result = run_command(cmd)
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
        raw = payload.get("format", {}).get("duration")
        return float(raw) if raw is not None else None
    except Exception:  # noqa: BLE001
        return None


def process_file(audio_file: Path, keyfinder_cli: Path, keep_temp: bool, ffmpeg_bin: str) -> dict[str, str]:
    wav_file = None
    remove_wav = False
    key = "UNK"
    bpm = "UNK"
    key_error = ""
    bpm_error = ""
    try:
        wav_file, remove_wav = convert_to_analysis_wav(audio_file, keep_temp, ffmpeg_bin)
        key = detect_key_with_cli(keyfinder_cli, wav_file)
    except Exception as exc:  # noqa: BLE001
        key_error = str(exc)
    finally:
        if wav_file and remove_wav and wav_file.exists():
            wav_file.unlink()

    try:
        bpm = str(detect_bpm(audio_file))
    except Exception as exc:  # noqa: BLE001
        bpm_error = str(exc)

    original_stem = re.sub(r"\s+\[[^\]]+\]$", "", audio_file.stem)
    suffix_tag = sanitize_for_filename(f"{key}-{bpm}")
    renamed = unique_path(audio_file.with_name(f"{original_stem} [{suffix_tag}]{audio_file.suffix}"))
    audio_file.rename(renamed)

    return {
        "input": audio_file.name,
        "output": renamed.name,
        "key": key,
        "bpm": bpm,
        "key_error": key_error,
        "bpm_error": bpm_error,
    }


def run_job(config: JobConfig, progress: ProgressCallback | None = None, should_cancel: Callable[[], bool] | None = None) -> dict:
    def emit(event: dict) -> None:
        if progress is not None:
            progress(event)

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    yt_dlp_cmd, ffmpeg_bin, ffprobe_bin = ensure_dependencies()
    ffmpeg_location = str(Path(ffmpeg_bin).parent)
    emit({"stage": "downloading", "message": "Starting download"})
    files, skipped_items = download_audio(yt_dlp_cmd, config, ffmpeg_location=ffmpeg_location, progress=emit)
    report = list(skipped_items)
    if not files and not report:
        raise RuntimeError("No audio files were downloaded.")

    total = len(files)
    for idx, audio_file in enumerate(files, start=1):
        if cancelled():
            emit({"stage": "cancelled", "message": "Job cancelled by user"})
            return {"status": "cancelled", "items": report}

        duration_seconds = get_audio_duration_seconds(audio_file, ffprobe_bin)
        if duration_seconds is not None and duration_seconds > MAX_ANALYSIS_SECONDS:
            deleted = False
            delete_error = ""
            try:
                audio_file.unlink(missing_ok=True)
                deleted = True
            except Exception as exc:  # noqa: BLE001
                delete_error = str(exc)
            skip_item = {
                "input": audio_file.name,
                "output": audio_file.name,
                "key": "SKIPPED",
                "bpm": "SKIPPED",
                "key_error": "",
                "bpm_error": "",
                "skipped": True,
                "skip_reason": "duration_over_10_minutes",
                "duration_seconds": int(round(duration_seconds)),
                "deleted": deleted,
                "delete_error": delete_error,
            }
            report.append(skip_item)
            emit(
                {
                    "stage": "skipped",
                    "index": idx,
                    "total": total,
                    "file": audio_file.name,
                    "message": "Skipped file longer than 10 minutes",
                }
            )
            continue

        emit({"stage": "processing", "index": idx, "total": total, "file": audio_file.name})
        item = process_file(audio_file, config.keyfinder_cli, config.keep_temp, ffmpeg_bin)
        report.append(item)
        emit({"stage": "processed", "index": idx, "total": total, "item": item})

    emit({"stage": "complete", "message": "All files processed", "count": len(report)})
    return {"status": "completed", "items": report}
