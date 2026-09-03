"""
Orchestrates one video-processing job end to end: DB status transitions
+ calling the CV pipeline (app.worker.pipeline.video_processor). This
used to be a bare `run_job(job_id)` function in tasks.py; pulled out
into a class so:

  * the DB/queue side (this file) is unit-testable with a fake
    `process_video` callable, independently of RQ actually running;
  * `app/worker/tasks.py` stays a 3-line adapter matching the string
    path RQ needs (`"app.worker.tasks.run_job"`, see queue.py), which
    is the only reason that module exists at all.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable

from app.repositories.job_repository import JobRepository
from app.services.storage import StorageService
from app.worker.pipeline.video_processor import ProcessingResult, process_video

log = logging.getLogger(__name__)

ProcessVideoFn = Callable[..., ProcessingResult]


class JobRunner:
    """Runs a single job. One instance is created per job execution
    (see app/worker/tasks.py) - it is not shared/reused across jobs."""

    def __init__(
        self,
        repository: JobRepository | None = None,
        storage: StorageService | None = None,
        process_video_fn: ProcessVideoFn = process_video,
    ):
        self._repository = repository or JobRepository()
        self._storage = storage or StorageService()
        self._process_video_fn = process_video_fn

    def run(self, job_id: str) -> None:
        job = self._repository.get(job_id)
        if job is None:
            log.error("Job %s not found", job_id)
            return

        self._repository.mark_processing(job_id)
        out_path = self._storage.output_path_for(job_id)

        try:
            result = self._process_video_fn(
                job.input_path,
                str(out_path),
                progress_cb=self._make_progress_cb(job_id),
            )
            self._repository.mark_done(
                job_id,
                output_path=str(out_path),
                bag_count=result.bag_count,
                anomalies=result.anomalies,
                total_frames=result.total_frames,
                fps=result.fps,
            )
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any
            # failure of the CV pipeline must still leave the job in a
            # terminal, inspectable state rather than stuck "processing".
            log.exception("Job %s failed", job_id)
            self._repository.mark_failed(job_id, error=f"{exc}\n{traceback.format_exc()[-2000:]}")

    def _make_progress_cb(self, job_id: str) -> Callable[[int, int], None]:
        def progress_cb(done: int, total: int) -> None:
            self._repository.update_progress(job_id, processed_frames=done, total_frames=total)

        return progress_cb
