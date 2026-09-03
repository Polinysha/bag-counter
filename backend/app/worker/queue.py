import redis
from rq import Queue

from app.config import settings

# health_check_interval + socket_keepalive: without these, an idle
# connection (e.g. the worker's pubsub listener with nothing queued)
# can get silently dropped by NAT/firewalls (observed on Docker
# Desktop for Windows after a few minutes of inactivity), which the
# rq worker reports as "Redis connection timeout, quitting..." and
# restarts from. Sending periodic pings keeps the connection alive.
redis_conn = redis.from_url(
    settings.redis_url,
    health_check_interval=30,
    socket_keepalive=True,
    socket_timeout=None,
)
task_queue = Queue(
    settings.queue_name,
    connection=redis_conn,
    default_timeout=settings.job_timeout_seconds,
)
