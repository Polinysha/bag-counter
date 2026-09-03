"""Redis/RQ connection and queue, wrapped in a class so call sites
depend on `TaskQueue`, not on module-level globals - makes it mockable
in VideoService unit tests (see backend/tests/unit/test_video_service.py)."""

from __future__ import annotations

import redis
from rq import Queue

from app.config import settings


class TaskQueue:
    """Thin wrapper around the RQ queue used for video-processing jobs.

    health_check_interval + socket_keepalive: without these, an idle
    connection (e.g. the worker's pubsub listener with nothing queued)
    can get silently dropped by NAT/firewalls (observed on Docker
    Desktop for Windows after a few minutes of inactivity), which the
    rq worker reports as "Redis connection timeout, quitting..." and
    restarts from. Sending periodic pings keeps the connection alive.
    """

    _redis_conn: redis.Redis | None = None
    _queue: Queue | None = None

    def __init__(self):
        cls = type(self)
        if cls._redis_conn is None:
            cls._redis_conn = redis.from_url(
                settings.redis_url,
                health_check_interval=30,
                socket_keepalive=True,
                socket_timeout=None,
            )
        if cls._queue is None:
            cls._queue = Queue(
                settings.queue_name,
                connection=cls._redis_conn,
                default_timeout=settings.job_timeout_seconds,
            )

    @property
    def redis_conn(self) -> redis.Redis:
        return type(self)._redis_conn  # type: ignore[return-value]

    @property
    def queue(self) -> Queue:
        return type(self)._queue  # type: ignore[return-value]

    def enqueue_video_job(self, job_id: str) -> None:
        self.queue.enqueue("app.worker.tasks.run_job", job_id, job_id=f"job-{job_id}")
