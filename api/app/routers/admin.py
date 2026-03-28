"""Admin endpoints for triggering scrape, elo recompute, and model retrain."""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBasic()

# Simple in-memory job status tracking
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# Per-job log buffers (max 500 lines each)
_logs: dict[str, deque[str]] = {}
MAX_LOG_LINES = 500


class _JobLogHandler(logging.Handler):
    """Captures log records into a per-job buffer."""

    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        with _lock:
            if self.job_id not in _logs:
                _logs[self.job_id] = deque(maxlen=MAX_LOG_LINES)
            _logs[self.job_id].append(line)


def _verify_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    settings = get_settings()
    if credentials.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username


def _run_in_background(job_id: str, func, **kwargs) -> dict:
    """Start a job in a background thread and return its status."""
    with _lock:
        existing = _jobs.get(job_id)
        if existing and existing["status"] == "running":
            return existing

    # Set up log capture for this job
    handler = _JobLogHandler(job_id)
    with _lock:
        _logs[job_id] = deque(maxlen=MAX_LOG_LINES)

    def _worker():
        # Attach handler to app loggers (not uvicorn/root to avoid feedback loop)
        app_logger = logging.getLogger("app")
        app_logger.setLevel(logging.DEBUG)
        app_logger.addHandler(handler)
        with _lock:
            _jobs[job_id] = {
                "status": "running",
                "started_at": datetime.now(UTC).isoformat(),
                "result": None,
                "error": None,
            }
        try:
            handler.emit(logging.LogRecord(
                "admin", logging.INFO, "", 0,
                f"Job '{job_id}' started", (), None,
            ))
            result = func(**kwargs)
            with _lock:
                _jobs[job_id]["status"] = "completed"
                _jobs[job_id]["result"] = result
                _jobs[job_id]["completed_at"] = datetime.now(UTC).isoformat()
            handler.emit(logging.LogRecord(
                "admin", logging.INFO, "", 0,
                f"Job '{job_id}' completed: {result}", (), None,
            ))
        except Exception as e:
            logger.exception("Job %s failed", job_id)
            with _lock:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = str(e)
                _jobs[job_id]["completed_at"] = datetime.now(UTC).isoformat()
            handler.emit(logging.LogRecord(
                "admin", logging.ERROR, "", 0,
                f"Job '{job_id}' failed: {e}", (), None,
            ))
        finally:
            app_logger.removeHandler(handler)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    with _lock:
        return _jobs[job_id]


def _scrape_task(pages: int = 5) -> dict:
    from app.services.scraper import scrape_recent_matches

    _job_log("scrape", "Starting scrape with %d pages...", pages)
    count = scrape_recent_matches(pages=pages)
    _job_log("scrape", "Scrape finished: %d new matches", count)
    return {"new_matches": count}


def _elo_task_inner() -> dict:
    from app.services.compute_elo import compute_all_elo

    _job_log("elo", "Starting Elo recomputation...")
    compute_all_elo()
    _job_log("elo", "Elo recomputation complete")
    return {"status": "done"}


def _retrain_task_inner() -> dict:
    from app.ml.train import train_and_save

    _job_log("retrain", "Starting model training...")
    metadata = train_and_save()
    _job_log("retrain", "Training complete: version=%s", metadata.get("model_version"))
    return {
        "model_version": metadata.get("model_version"),
        "row_count": metadata.get("row_count"),
        "test_accuracy": metadata.get("test", {}).get("full_model", {}).get("accuracy"),
    }


def _job_log(job_id: str, msg: str, *args):
    """Write directly to a job's log buffer."""
    formatted = msg % args if args else msg
    ts = datetime.now(UTC).strftime("%H:%M:%S")
    line = f"{ts} INFO admin: {formatted}"
    with _lock:
        if job_id not in _logs:
            _logs[job_id] = deque(maxlen=MAX_LOG_LINES)
        _logs[job_id].append(line)


def _elo_task() -> dict:
    return _elo_task_inner()


def _retrain_task() -> dict:
    return _retrain_task_inner()


@router.post("/scrape")
async def trigger_scrape(
    pages: int = Query(5, ge=1, le=100),
    _user: str = Depends(_verify_admin),
):
    """Scrape recent VLR results."""
    return _run_in_background("scrape", _scrape_task, pages=pages)


@router.post("/elo")
async def trigger_elo(_user: str = Depends(_verify_admin)):
    """Recompute all Elo ratings."""
    return _run_in_background("elo", _elo_task)


@router.post("/retrain")
async def trigger_retrain(_user: str = Depends(_verify_admin)):
    """Retrain the prediction model."""
    return _run_in_background("retrain", _retrain_task)


@router.post("/backfill-logos")
async def backfill_logos(
    logos: dict[str, str],
    _user: str = Depends(_verify_admin),
):
    """Bulk-import team logos. Body: {"team_name": "logo_url", ...}"""
    from app.database import SyncSessionLocal
    from sqlalchemy import text

    db = SyncSessionLocal()
    updated = 0
    try:
        for name, url in logos.items():
            r = db.execute(
                text("UPDATE teams SET logo_url = :url WHERE name = :name AND logo_url IS NULL"),
                {"name": name, "url": url},
            )
            updated += r.rowcount
        db.commit()
    finally:
        db.close()
    return {"updated": updated, "submitted": len(logos)}


@router.get("/status")
async def get_status(_user: str = Depends(_verify_admin)):
    """Get status of all jobs."""
    with _lock:
        return dict(_jobs)


@router.get("/logs/{job_id}")
async def get_logs(
    job_id: str,
    since: int = Query(0, ge=0),
    _user: str = Depends(_verify_admin),
):
    """Get log lines for a job. Use `since` to get only new lines (pass the last count you received)."""
    with _lock:
        buf = _logs.get(job_id)
        if buf is None:
            return {"lines": [], "total": 0}
        all_lines = list(buf)
        return {"lines": all_lines[since:], "total": len(all_lines)}
