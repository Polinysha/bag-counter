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

from fastapi import UploadFile

from app.models import Job, JobStatus
from app.repositories.job_repository import JobNotFoundError, JobRepository
from app.services.storage import StorageService
from app.worker.queue import TaskQueue


class InvalidUploadError(ValueError):
    pass


class JobAlreadyProcessingError(RuntimeError):
    def __init__(self, job_id: str):
        super().__init__(f"Job {job_id!r} is already processing")
        self.job_id = job_id


class VideoService:
    def __init__(
        self,
        repository: JobRepository,
        storage: StorageService,
        task_queue: TaskQueue,
    ):
        self._repository = repository
        self._storage = storage
        self._task_queue = task_queue

    def upload(self, file: UploadFile) -> Job:
        if not file.filename:
            raise InvalidUploadError("Missing filename")

        job = self._repository.create(original_filename=file.filename)
        path = self._storage.save_upload(job.id, file)
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
    "JobAlreadyProcessingError",
    "ResultNotReadyError",
    "JobNotFoundError",
    "build_video_service",
]
