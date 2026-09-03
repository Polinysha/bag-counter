"""
Entry point for the worker container.

We don't use the bare `rq worker --url ...` CLI because it builds its
own Redis connection from the URL alone, bypassing the
health_check_interval / socket_keepalive settings in
app/worker/queue.py. Without those, an idle connection (nothing in
the queue) can get silently dropped by NAT/firewalls after a few
minutes - observed on Docker Desktop for Windows - which RQ reports
as "Redis connection timeout, quitting..." and restarts from. Running
the Worker programmatically with our tuned connection avoids that.
"""
import logging

from rq import Worker

from app.config import settings
from app.worker.queue import redis_conn

logging.basicConfig(level=logging.INFO)


def main() -> None:
    worker = Worker(
        [settings.queue_name],
        connection=redis_conn,
    )
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
