"""In-process job runner over the `jobs` table (SPEC 5.3, D-003).

Render's free tier has no worker, so jobs are DB rows run by an asyncio task in the API process.
Jobs survive restarts: anything left RUNNING when the process starts is re-queued.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Job

log = logging.getLogger("briefpay.jobs")

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 30)  # after attempt 1, after attempt 2

Handler = Callable[[Session, dict], dict | None]
HANDLERS: dict[str, Handler] = {}


def register(job_type: str):
    """Decorator: @register("BA_RUN") def handle(db, payload): ..."""
    def deco(fn: Handler) -> Handler:
        HANDLERS[job_type] = fn
        return fn
    return deco


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(db: Session, job_type: str, payload: dict, run_after: datetime | None = None) -> Job:
    job = Job(type=job_type, payload_json=payload, state="QUEUED", run_after=run_after or _now())
    db.add(job)
    db.flush()
    return job


def recover_stuck(session_factory: Callable[[], Session]) -> int:
    """Called at startup: a job left RUNNING means the process died mid-run."""
    db = session_factory()
    try:
        res = db.execute(update(Job).where(Job.state == "RUNNING").values(state="QUEUED"))
        db.commit()
        return res.rowcount or 0
    finally:
        db.close()


def run_one(session_factory: Callable[[], Session]) -> bool:
    """Claim and run at most one due job. Returns True if a job was processed."""
    db = session_factory()
    try:
        job = db.scalars(
            select(Job).where(Job.state == "QUEUED", Job.run_after <= _now()).order_by(Job.id).limit(1)
        ).first()
        if job is None:
            return False
        job.state, job.attempts = "RUNNING", job.attempts + 1
        db.commit()
        job_id, job_type, payload, attempts = job.id, job.type, dict(job.payload_json), job.attempts
    finally:
        db.close()

    handler = HANDLERS.get(job_type)
    work = session_factory()
    try:
        if handler is None:
            raise LookupError(f"no handler registered for job type {job_type}")
        result = handler(work, payload)
        work.commit()
        outcome = ("DONE", result, None)
    except Exception as e:  # noqa: BLE001 - a job must never kill the runner
        work.rollback()
        log.exception("job %s (%s) failed on attempt %s", job_id, job_type, attempts)
        outcome = ("FAILED", None, f"{type(e).__name__}: {e}")
    finally:
        work.close()

    state, result, error = outcome
    db = session_factory()
    try:
        job = db.get(Job, job_id)
        if state == "FAILED" and attempts < MAX_ATTEMPTS:
            delay = BACKOFF_SECONDS[min(attempts - 1, len(BACKOFF_SECONDS) - 1)]
            job.state, job.run_after = "QUEUED", _now() + timedelta(seconds=delay)
        else:
            job.state = state
        job.result_json, job.last_error = result, error
        db.commit()
    finally:
        db.close()
    return True


class JobRunner:
    """Polls the table from FastAPI's lifespan. Handlers are sync, so each runs in a worker thread."""

    def __init__(self, session_factory: Callable[[], Session], poll_seconds: float = 1.0):
        self.session_factory = session_factory
        self.poll_seconds = poll_seconds
        self._task: asyncio.Task | None = None

    async def _loop(self) -> None:
        while True:
            try:
                did_work = await asyncio.to_thread(run_one, self.session_factory)
            except Exception:  # noqa: BLE001
                log.exception("job runner iteration failed")
                did_work = False
            if not did_work:
                await asyncio.sleep(self.poll_seconds)

    def start(self) -> None:
        recover_stuck(self.session_factory)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
