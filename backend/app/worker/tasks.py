import logging
import traceback
from datetime import datetime

from sqlmodel import Session

from app.db import engine
from app.models import Job, JobStatus
from app.services.storage import output_path_for
from app.worker.pipeline.video_processor import process_video

log = logging.getLogger(__name__)


def run_job(job_id: str) -> None:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            log.error("Job %s not found", job_id)
            return
        job.status = JobStatus.processing
        job.started_at = datetime.utcnow()
        session.add(job)
        session.commit()

    def progress_cb(done: int, total: int) -> None:
        with Session(engine) as s:
            j = s.get(Job, job_id)
            if j is None:
                return
            j.processed_frames = done
            j.total_frames = total
            j.progress_pct = round(100.0 * done / total, 1) if total else 0.0
            s.add(j)
            s.commit()

    out_path = output_path_for(job_id)
    try:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            input_path = job.input_path

        result = process_video(input_path, str(out_path), progress_cb=progress_cb)

        with Session(engine) as session:
            job = session.get(Job, job_id)
            job.status = JobStatus.done
            job.finished_at = datetime.utcnow()
            job.output_path = str(out_path)
            job.bag_count = result.bag_count
            job.anomalies = result.anomalies
            job.total_frames = result.total_frames
            job.processed_frames = result.total_frames
            job.fps = result.fps
            job.progress_pct = 100.0
            session.add(job)
            session.commit()

    except Exception as exc:  # noqa: BLE001
        log.exception("Job %s failed", job_id)
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job:
                job.status = JobStatus.failed
                job.error = f"{exc}\n{traceback.format_exc()[-2000:]}"
                job.finished_at = datetime.utcnow()
                session.add(job)
                session.commit()
