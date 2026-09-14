"""
API-level tests: exercise app/api/routes_videos.py through FastAPI's
TestClient with `build_video_service` overridden by a fake in-memory
`VideoService`, so these need neither Redis, SQLite-on-disk, nor the
MMDetection stack. Marked `integration` (see pyproject.toml) because
they still go through the full FastAPI dependency-injection + routing
stack, unlike backend/tests/unit/*.
"""

import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Job, JobStatus
from app.repositories.job_repository import JobNotFoundError, JobPage
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

    def list_jobs(self, *, limit: int, offset: int):
        all_jobs = list(self._jobs.values())
        return JobPage(items=all_jobs[offset : offset + limit], total=len(all_jobs))

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


class SequentialGetStatusFake:
    """Minimal VideoService stand-in used only by the SSE tests below.

    get_status() returns a pre-scripted sequence of Job snapshots, one
    per call (holding on the last one for any extra calls beyond the
    list's length). This sidesteps real-time race conditions between
    test-side status mutation and the server's async polling loop -
    the interesting behavior (each SSE frame reflects one read, the
    stream stops at a terminal status) is fully deterministic this
    way, independent of sleep timing.
    """

    def __init__(self, jobs: list[Job]):
        self._jobs = jobs
        self.calls = 0

    def get_status(self, job_id: str) -> Job:
        idx = min(self.calls, len(self._jobs) - 1)
        self.calls += 1
        return self._jobs[idx]


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


def test_health_endpoint_ok_when_dependencies_up(client, monkeypatch):
    # app.main imports check_db/check_redis by name, so patch them there
    # (patching app.health.check_db would not affect the already-bound
    # reference main.py holds).
    monkeypatch.setattr("app.main.check_db", lambda: True)
    monkeypatch.setattr("app.main.check_redis", lambda: True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"db": True, "redis": True}}


def test_health_endpoint_503_when_redis_down(client, monkeypatch):
    monkeypatch.setattr("app.main.check_db", lambda: True)
    monkeypatch.setattr("app.main.check_redis", lambda: False)
    resp = client.get("/api/health")
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "checks": {"db": True, "redis": False}}


def test_videos_route_open_when_no_api_key_configured(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_key", None)
    resp = client.get("/api/v1/videos")
    assert resp.status_code == 200


def test_videos_route_401_without_key_when_configured(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_key", "expected-secret")
    resp = client.get("/api/v1/videos")
    assert resp.status_code == 401


def test_videos_route_200_with_correct_key(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_key", "expected-secret")
    resp = client.get("/api/v1/videos", headers={"X-API-Key": "expected-secret"})
    assert resp.status_code == 200


def test_health_endpoint_unauthenticated_even_when_api_key_configured(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_key", "expected-secret")
    monkeypatch.setattr("app.main.check_db", lambda: True)
    monkeypatch.setattr("app.main.check_redis", lambda: True)
    resp = client.get("/api/health")  # no X-API-Key header
    assert resp.status_code == 200


def test_list_videos_returns_paginated_envelope(client):
    for _ in range(3):
        client.post("/api/v1/videos", files={"file": ("clip.mp4", BytesIO(b"x"), "video/mp4")})

    resp = client.get("/api/v1/videos?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2


def test_list_videos_default_pagination_params(client):
    resp = client.get("/api/v1/videos")
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 50
    assert body["offset"] == 0


def test_list_videos_rejects_limit_above_max(client):
    resp = client.get("/api/v1/videos?limit=99999")
    assert resp.status_code == 422


def test_list_videos_rejects_negative_offset(client):
    resp = client.get("/api/v1/videos?offset=-1")
    assert resp.status_code == 422


def test_events_404_for_unknown_job(client):
    resp = client.get("/api/v1/videos/does-not-exist/events")
    assert resp.status_code == 404


def test_events_stream_reflects_terminal_status_and_closes(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sse_poll_interval_seconds", 0.01)
    job = Job(id="job-1", original_filename="clip.mp4", input_path="/x", status=JobStatus.done)
    fake = SequentialGetStatusFake([job])
    app.dependency_overrides[build_video_service] = lambda: fake
    try:
        with (
            TestClient(app) as client,
            client.stream("GET", "/api/v1/videos/job-1/events") as response,
        ):
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            lines = [line for line in response.iter_lines() if line]
    finally:
        app.dependency_overrides.clear()

    assert len(lines) == 1  # terminal status -> exactly one event, then close
    assert lines[0].startswith("data: ")
    payload = json.loads(lines[0][len("data: ") :])
    assert payload["status"] == "done"
    assert payload["id"] == "job-1"


def test_events_stream_pushes_update_when_status_changes(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sse_poll_interval_seconds", 0.01)
    processing = Job(
        id="job-1", original_filename="clip.mp4", input_path="/x", status=JobStatus.processing
    )
    failed = Job(id="job-1", original_filename="clip.mp4", input_path="/x", status=JobStatus.failed)
    # [existence pre-check, 1st stream read, 2nd stream read] - see
    # stream_status() in routes_videos.py for why the pre-check exists.
    fake = SequentialGetStatusFake([processing, processing, failed])
    app.dependency_overrides[build_video_service] = lambda: fake
    try:
        with (
            TestClient(app) as client,
            client.stream("GET", "/api/v1/videos/job-1/events") as response,
        ):
            lines = [line for line in response.iter_lines() if line]
    finally:
        app.dependency_overrides.clear()

    assert len(lines) == 2
    first = json.loads(lines[0][len("data: ") :])
    second = json.loads(lines[1][len("data: ") :])
    assert first["status"] == "processing"
    assert second["status"] == "failed"  # terminal - stream stopped here
