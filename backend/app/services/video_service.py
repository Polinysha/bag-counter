"""
Application/orchestration layer for the video-job use cases exposed by
the API (app/api/routes_videos.py). Routes stay thin: parse the
request, call one `VideoService` method, map the result/exception onto
an HTTP response. All the actual decisions (validation, what "already
processing" means, enqueueing) live here so they're unit-testable
without spinning up FastAPI, and so a future second transport (a CLI,
a gRPC endpoint, a batch script) can reuse the exact same logic.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from fastapi import UploadFile

from app.models import Job, JobStatus
from app.repositories.job_repository import JobNotFoundError, JobRepository
from app.services.storage import StorageService, UploadTooLargeError
from app.worker.queue import TaskQueue


class JobRepositoryProtocol(Protocol):
    """Structural type for the repository dependency VideoService needs.

    JobRepository (app/repositories/job_repository.py) satisfies this
    implicitly - no inheritance needed. Defined so unit tests
    (tests/unit/test_video_service.py) can pass a plain in-memory fake
    without either subclassing JobRepository or reaching for
    `# type: ignore` at every call site.
    """

    def create(self, *, original_filename: str) -> Job: ...
    def get_or_raise(self, job_id: str) -> Job: ...
    def set_input_path(self, job_id: str, input_path: str) -> Job: ...
    def mark_queued(self, job_id: str) -> Job: ...
    def mark_failed(self, job_id: str, *, error: str) -> None: ...
    def list_all(self) -> Sequence[Job]: ...


class StorageServiceProtocol(Protocol):
    def save_upload(self, job_id: str, file: UploadFile): ...


class TaskQueueProtocol(Protocol):
    def enqueue_video_job(self, job_id: str) -> None: ...


class InvalidUploadError(ValueError):
    pass


class UploadTooLargeServiceError(InvalidUploadError):
    """Distinct from InvalidUploadError so routes_videos.py can map it to
    413 instead of 400 - it's still a ValueError/InvalidUploadError so
    any caller that only checks for the base class keeps working."""


class JobAlreadyProcessingError(RuntimeError):
    def __init__(self, job_id: str):
        super().__init__(f"Job {job_id!r} is already processing")
        self.job_id = job_id


class VideoService:
    def __init__(
        self,
        repository: JobRepositoryProtocol,
        storage: StorageServiceProtocol,
        task_queue: TaskQueueProtocol,
    ):
        self._repository = repository
        self._storage = storage
        self._task_queue = task_queue

    def upload(self, file: UploadFile) -> Job:
        if not file.filename:
            raise InvalidUploadError("Missing filename")

        job = self._repository.create(original_filename=file.filename)
        try:
            path = self._storage.save_upload(job.id, file)
        except UploadTooLargeError as exc:
            # The Job row already exists (created above) - rather than
            # deleting it (losing the audit trail of "someone tried"),
            # mark it failed so it's visible in GET /videos like any
            # other failure, then surface a 413 to the caller.
            self._repository.mark_failed(job.id, error=str(exc))
            raise UploadTooLargeServiceError(str(exc)) from exc
        return self._repository.set_input_path(job.id, str(path))

    def start_processing(self, job_id: str) -> Job:
        job = self._repository.get_or_raise(job_id)
        if job.status == JobStatus.processing:
            raise JobAlreadyProcessingError(job_id)

        job = self._repository.mark_queued(job_id)
        self._task_queue.enqueue_video_job(job_id)
        return job

    def get_status(self, job_id: str) -> Job:
        return self._repository.get_or_raise(job_id)

    def get_anomalies(self, job_id: str) -> Job:
        return self._repository.get_or_raise(job_id)

    def list_jobs(self) -> list[Job]:
        return list(self._repository.list_all())

    def get_result_path(self, job_id: str) -> tuple[Job, str]:
        job = self._repository.get_or_raise(job_id)
        if job.status != JobStatus.done or not job.output_path:
            raise ResultNotReadyError(job_id)
        return job, job.output_path


class ResultNotReadyError(RuntimeError):
    def __init__(self, job_id: str):
        super().__init__(f"Result for job {job_id!r} is not ready yet")
        self.job_id = job_id


def build_video_service() -> VideoService:
    """FastAPI dependency factory - see app/api/routes_videos.py."""
    return VideoService(
        repository=JobRepository(),
        storage=StorageService(),
        task_queue=TaskQueue(),
    )


__all__ = [
    "VideoService",
    "InvalidUploadError",
    "UploadTooLargeServiceError",
    "JobAlreadyProcessingError",
    "ResultNotReadyError",
    "JobNotFoundError",
    "build_video_service",
]
