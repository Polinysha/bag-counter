"""Unit tests for VideoService (app/services/video_service.py) using
in-memory fakes for JobRepository/StorageService/TaskQueue - exercises
the orchestration logic (what counts as "already processing", how an
oversized upload is surfaced) without a DB, queue, or FastAPI."""

from __future__ import annotations

import io

import pytest
from fastapi import UploadFile

from app.models import Job, JobStatus
from app.repositories.job_repository import JobNotFoundError
from app.services.storage import UploadTooLargeError
from app.services.video_service import (
    JobAlreadyProcessingError,
    UploadTooLargeServiceError,
    VideoService,
)


class FakeRepository:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._next_id = 1
        self.failed_calls: list[tuple[str, str]] = []

    def create(self, *, original_filename: str) -> Job:
        job_id = str(self._next_id)
        self._next_id += 1
        job = Job(id=job_id, original_filename=original_filename, input_path="")
        self.jobs[job_id] = job
        return job

    def get_or_raise(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def set_input_path(self, job_id: str, input_path: str) -> Job:
        self.jobs[job_id].input_path = input_path
        return self.jobs[job_id]

    def mark_queued(self, job_id: str) -> Job:
        self.jobs[job_id].status = JobStatus.queued
        return self.jobs[job_id]

    def mark_failed(self, job_id: str, *, error: str) -> None:
        self.failed_calls.append((job_id, error))
        self.jobs[job_id].status = JobStatus.failed
        self.jobs[job_id].error = error

    def list_all(self) -> list[Job]:
        return list(self.jobs.values())


class FakeStorage:
    def __init__(self, *, raise_too_large: bool = False):
        self._raise_too_large = raise_too_large

    def save_upload(self, job_id: str, file: UploadFile):
        if self._raise_too_large:
            raise UploadTooLargeError(max_mb=1)
        return f"/data/uploads/{job_id}.mp4"


class FakeTaskQueue:
    def __init__(self):
        self.enqueued: list[str] = []

    def enqueue_video_job(self, job_id: str) -> None:
        self.enqueued.append(job_id)


def _upload_file() -> UploadFile:
    return UploadFile(filename="clip.mp4", file=io.BytesIO(b"data"))


def test_upload_too_large_marks_job_failed_and_raises_service_error():
    repo = FakeRepository()
    service = VideoService(repo, FakeStorage(raise_too_large=True), FakeTaskQueue())

    with pytest.raises(UploadTooLargeServiceError):
        service.upload(_upload_file())

    # job record kept (audit trail), marked failed rather than silently dropped
    ((job_id, _error),) = repo.failed_calls
    assert repo.jobs[job_id].status == JobStatus.failed


def test_start_processing_twice_raises_already_processing():
    repo = FakeRepository()
    queue = FakeTaskQueue()
    service = VideoService(repo, FakeStorage(), queue)

    job = service.upload(_upload_file())
    service.start_processing(job.id)
    repo.jobs[job.id].status = JobStatus.processing

    with pytest.raises(JobAlreadyProcessingError):
        service.start_processing(job.id)


def test_start_processing_enqueues_exactly_once():
    repo = FakeRepository()
    queue = FakeTaskQueue()
    service = VideoService(repo, FakeStorage(), queue)

    job = service.upload(_upload_file())
    service.start_processing(job.id)

    assert queue.enqueued == [job.id]
