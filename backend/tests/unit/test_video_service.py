"""Unit tests for VideoService (app/services/video_service.py) using
in-memory fakes for JobRepository/StorageService/TaskQueue - exercises
the orchestration logic (what counts as "already processing", how an
oversized upload is surfaced) without a DB, queue, or FastAPI."""

from __future__ import annotations

import io

import pytest
from fastapi import UploadFile

from app.models import Job, JobStatus
from app.repositories.job_repository import JobNotFoundError, JobPage
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

    def list_page(self, *, limit: int, offset: int) -> JobPage:
        # newest-first, matching JobRepository.list_page's ordering
        all_jobs = sorted(self.jobs.values(), key=lambda j: j.id, reverse=True)
        return JobPage(items=all_jobs[offset : offset + limit], total=len(all_jobs))


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


def test_list_jobs_returns_page_and_total():
    repo = FakeRepository()
    service = VideoService(repo, FakeStorage(), FakeTaskQueue())
    for _ in range(5):
        service.upload(_upload_file())

    page = service.list_jobs(limit=2, offset=0)
    assert len(page.items) == 2
    assert page.total == 5


def test_list_jobs_offset_beyond_total_returns_empty_page():
    repo = FakeRepository()
    service = VideoService(repo, FakeStorage(), FakeTaskQueue())
    service.upload(_upload_file())

    page = service.list_jobs(limit=10, offset=100)
    assert page.items == []
    assert page.total == 1


def test_list_jobs_rejects_limit_below_one():
    repo = FakeRepository()
    service = VideoService(repo, FakeStorage(), FakeTaskQueue())
    with pytest.raises(ValueError, match="limit"):
        service.list_jobs(limit=0, offset=0)


def test_list_jobs_rejects_limit_above_max():
    repo = FakeRepository()
    service = VideoService(repo, FakeStorage(), FakeTaskQueue())
    with pytest.raises(ValueError, match="limit"):
        service.list_jobs(limit=VideoService.MAX_PAGE_SIZE + 1, offset=0)


def test_list_jobs_rejects_negative_offset():
    repo = FakeRepository()
    service = VideoService(repo, FakeStorage(), FakeTaskQueue())
    with pytest.raises(ValueError, match="offset"):
        service.list_jobs(limit=10, offset=-1)
