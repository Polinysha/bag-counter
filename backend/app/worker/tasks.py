"""
RQ entrypoint. Kept as a free function purely because RQ jobs are
enqueued by dotted-path string (`"app.worker.tasks.run_job"`, see
app/worker/queue.py::TaskQueue.enqueue_video_job) and resolved by
`importlib` on the worker side - it cannot resolve a bound method.
All actual logic lives in `JobRunner` (app/worker/job_runner.py).
"""

from app.worker.job_runner import JobRunner


def run_job(job_id: str) -> None:
    JobRunner().run(job_id)
