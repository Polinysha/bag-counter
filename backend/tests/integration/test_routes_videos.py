"""
API-level tests: exercise app/api/routes_videos.py through FastAPI's
TestClient with `build_video_service` overridden by a fake in-memory
`VideoService`, so these need neither Redis, SQLite-on-disk, nor the
MMDetection stack. Marked `integration` (see pyproject.toml) because
they still go through the full FastAPI dependency-injection + routing
stack, unlike backend/tests/unit/*.
"""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Job, JobStatus
from app.repositories.job_repository import JobNotFoundError
from app.services.video_service import (
    JobAlreadyProcessingError,
    ResultNotReadyError,
    build_video_service,
)

pytestmark = pytest.mark.integration


class FakeVideoService:
    """In-memory stand-in for VideoService, good enough to exercise the
    route/HTTP-status-code contract without a DB or a queue."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._next_id = 1

    def upload(self, file) -> Job:
        job_id = str(self._next_id)
        self._next_id += 1
        job = Job(id=job_id, original_filename=file.filename, input_path=f"/data/{job_id}.mp4")
        self._jobs[job_id] = job
        return job

    def start_processing(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job.status == JobStatus.processing:
            raise JobAlreadyProcessingError(job_id)
        job.status = JobStatus.queued
        return job

    def get_status(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def get_anomalies(self, job_id: str) -> Job:
        return self.get_status(job_id)

    def list_jobs(self):
        return list(self._jobs.values())

    def get_result_path(self, job_id: str):
        job = self.get_status(job_id)
        if job.status != JobStatus.done:
            raise ResultNotReadyError(job_id)
        return job, job.output_path


@pytest.fixture()
def client():
    fake = FakeVideoService()
    app.dependency_overrides[build_video_service] = lambda: fake
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_upload_returns_201_and_queued_job(client):
    resp = client.post(
        "/api/v1/videos", files={"file": ("clip.mp4", BytesIO(b"fake-bytes"), "video/mp4")}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "queued"
    assert "id" in body


def test_status_for_unknown_job_is_404(client):
    resp = client.get("/api/v1/videos/does-not-exist")
    assert resp.status_code == 404


def test_process_unknown_job_is_404(client):
    resp = client.post("/api/v1/videos/does-not-exist/process")
    assert resp.status_code == 404


def test_result_before_done_is_409(client):
    upload = client.post("/api/v1/videos", files={"file": ("clip.mp4", BytesIO(b"x"), "video/mp4")})
    job_id = upload.json()["id"]
    resp = client.get(f"/api/v1/videos/{job_id}/result")
    assert resp.status_code == 409


def test_health_endpoint_is_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
