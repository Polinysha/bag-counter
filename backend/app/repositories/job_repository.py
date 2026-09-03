"""
Data-access layer for `Job`. This is the ONLY module in the codebase
allowed to build SQLModel `select(...)` statements against `Job` -
routes (app/api), the RQ task entrypoint (app/worker/tasks.py) and the
job runner (app/worker/job_runner.py) all go through
`JobRepository`, never through `Session` directly. That keeps the
persistence shape (SQLite today, see README "Key Technical Decisions")
swappable behind one class instead of scattered across the codebase.

Each method opens/closes its own `Session` unless one is explicitly
passed in (`session=...`), so both request-scoped (FastAPI `Depends`)
and job-scoped (long-running worker) call sites can use it uniformly.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime

from sqlmodel import Session, select

from app.db import engine
from app.models import Job, JobStatus


class JobRepository:
    """Repository for `Job` persistence. Stateless; safe to instantiate
    per-request or reuse a single module-level instance."""

    def __init__(self, session: Session | None = None):
        self._external_session = session

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        if self._external_session is not None:
            yield self._external_session
            return
        with Session(engine) as session:
            yield session

    # --- reads -----------------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        with self._session_scope() as session:
            return session.get(Job, job_id)

    def get_or_raise(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def list_all(self) -> Sequence[Job]:
        with self._session_scope() as session:
            return session.exec(
                select(Job).order_by(Job.created_at.desc())  # type: ignore[attr-defined]
            ).all()

    # --- writes ------------------------------------------------------------

    def create(self, *, original_filename: str) -> Job:
        job = Job(original_filename=original_filename, input_path="")
        with self._session_scope() as session:
            session.add(job)
            session.commit()
            session.refresh(job)
        return job

    def set_input_path(self, job_id: str, input_path: str) -> Job:
        with self._session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            job.input_path = input_path
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def mark_queued(self, job_id: str) -> Job:
        with self._session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            job.status = JobStatus.queued
            job.error = None
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def mark_processing(self, job_id: str) -> None:
        with self._session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            job.status = JobStatus.processing
            job.started_at = datetime.utcnow()
            session.add(job)
            session.commit()

    def update_progress(self, job_id: str, *, processed_frames: int, total_frames: int) -> None:
        with self._session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.processed_frames = processed_frames
            job.total_frames = total_frames
            job.progress_pct = (
                round(100.0 * processed_frames / total_frames, 1) if total_frames else 0.0
            )
            session.add(job)
            session.commit()

    def mark_done(
        self,
        job_id: str,
        *,
        output_path: str,
        bag_count: int,
        anomalies: list,
        total_frames: int,
        fps: float,
    ) -> None:
        with self._session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = JobStatus.done
            job.finished_at = datetime.utcnow()
            job.output_path = output_path
            job.bag_count = bag_count
            job.anomalies = anomalies
            job.total_frames = total_frames
            job.processed_frames = total_frames
            job.fps = fps
            job.progress_pct = 100.0
            session.add(job)
            session.commit()

    def mark_failed(self, job_id: str, *, error: str) -> None:
        with self._session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            job.status = JobStatus.failed
            job.error = error
            job.finished_at = datetime.utcnow()
            session.add(job)
            session.commit()


class JobNotFoundError(LookupError):
    def __init__(self, job_id: str):
        super().__init__(f"Job {job_id!r} not found")
        self.job_id = job_id
