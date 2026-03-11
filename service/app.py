from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from scripts.downloader_core import JobConfig, run_job

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "service" / "state"
STATE_FILE = STATE_DIR / "jobs.json"
DEFAULT_OUTPUT_DIR = ROOT / "downloads"
DEFAULT_KEYFINDER = ROOT / "tools" / "keyfinder_cli" / "build" / "keyfinder_cli"
MAX_LOG_EVENTS = 200


class JobCreateRequest(BaseModel):
    url: str = Field(min_length=5)
    mode: str = Field(default="playlist")
    limit: int | None = Field(default=None, ge=1)
    target_dir: str | None = None
    audio_format: str = "mp3"
    keep_temp: bool = False
    keyfinder_cli: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be a valid http/https URL")
        return value


class JobCreateResponse(BaseModel):
    job_id: str
    status: str


@dataclass
class JobState:
    id: str
    request: dict[str, Any]
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    progress: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    logs: list[dict[str, Any]] = field(default_factory=list)
    cancel_requested: bool = False

    def touch(self) -> None:
        self.updated_at = time.time()


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._jobs: dict[str, JobState] = {}
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self._load_state()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _load_state(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            raw = json.loads(STATE_FILE.read_text())
            for item in raw.get("jobs", []):
                state = JobState(**item)
                self._jobs[state.id] = state
        except Exception:
            # Corrupt state should not block service startup.
            self._jobs = {}

    def _persist(self) -> None:
        payload = json.dumps({"jobs": [asdict(j) for j in self._jobs.values()]}, indent=2)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(payload)
        tmp.replace(STATE_FILE)

    def _update_job(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            job.touch()
            self._persist()

    def create_job(self, req: JobCreateRequest) -> JobState:
        if req.mode not in {"playlist", "single"}:
            raise ValueError("mode must be 'playlist' or 'single'")
        if req.mode == "single" and req.limit is not None:
            raise ValueError("limit is only valid for playlist mode")

        state = JobState(
            id=str(uuid.uuid4()),
            request=req.model_dump(),
            status="queued",
            progress={"stage": "queued"},
        )
        with self._lock:
            self._jobs[state.id] = state
            self._persist()
        self._queue.put(state.id)
        return state

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 20) -> list[JobState]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda x: x.created_at, reverse=True)
            return jobs[:limit]

    def cancel_job(self, job_id: str) -> JobState:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            job.cancel_requested = True
            if job.status == "queued":
                job.status = "cancelled"
                job.progress = {"stage": "cancelled", "message": "Cancelled before start"}
            job.touch()
            self._persist()
            return job

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.get_job(job_id)
            if job is None:
                continue
            if job.cancel_requested or job.status == "cancelled":
                continue
            self._run_job(job_id)

    def _run_job(self, job_id: str) -> None:
        self._update_job(job_id, status="running", progress={"stage": "starting"})
        job = self.get_job(job_id)
        assert job is not None
        req = job.request

        config = JobConfig(
            url=req["url"],
            mode=req["mode"],
            output_dir=Path(req.get("target_dir") or DEFAULT_OUTPUT_DIR),
            audio_format=req["audio_format"],
            keyfinder_cli=Path(req.get("keyfinder_cli") or DEFAULT_KEYFINDER),
            keep_temp=req["keep_temp"],
            limit=req.get("limit"),
        )

        def on_progress(evt: dict[str, Any]) -> None:
            with self._lock:
                state = self._jobs[job_id]
                state.progress = evt
                state.logs.append({"ts": time.time(), **evt})
                if len(state.logs) > MAX_LOG_EVENTS:
                    state.logs = state.logs[-MAX_LOG_EVENTS:]
                state.touch()
                self._persist()

        def should_cancel() -> bool:
            with self._lock:
                return self._jobs[job_id].cancel_requested

        try:
            result = run_job(config, progress=on_progress, should_cancel=should_cancel)
            final_status = result.get("status", "completed")
            self._update_job(job_id, status=final_status, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            self._update_job(
                job_id,
                status="failed",
                error=str(exc),
                progress={"stage": "failed", "message": str(exc)},
            )


manager = JobManager()
app = FastAPI(title="FL VST Companion Service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobCreateResponse)
def create_job(req: JobCreateRequest) -> JobCreateResponse:
    try:
        state = manager.create_job(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobCreateResponse(job_id=state.id, status=state.status)


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    state = manager.get_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return asdict(state)


@app.get("/jobs")
def list_jobs(limit: int = 20) -> dict[str, Any]:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    return {"jobs": [asdict(s) for s in manager.list_jobs(limit=limit)]}


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    try:
        state = manager.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return {"job_id": state.id, "status": state.status, "cancel_requested": state.cancel_requested}
