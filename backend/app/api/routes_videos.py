from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.db import get_session
from app.models import Job, JobStatus
from app.schemas import JobCreatedResponse, JobStatusResponse, JobAnomaliesResponse
from app.services.storage import save_upload
from app.worker.queue import task_queue

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("", response_model=JobCreatedResponse, status_code=201)
def upload_video(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """
    Upload a video. This only stores the file and creates a job record
    - it does NOT start processing (see POST /videos/{id}/process),
    so the upload itself is always fast regardless of video length.
    """
    if not file.filename:
        raise HTTPException(400, "Missing filename")

    job = Job(original_filename=file.filename, input_path="")
    session.add(job)
    session.commit()
    session.refresh(job)

    path = save_upload(job.id, file)
    job.input_path = str(path)
    session.add(job)
    session.commit()

    return JobCreatedResponse(id=job.id, status=job.status)


@router.post("/{job_id}/process", response_model=JobCreatedResponse)
def start_processing(job_id: str, session: Session = Depends(get_session)):
    """
    Enqueue the video for background processing and return immediately.
    The actual MMDetection inference happens in a separate worker
    process consuming the Redis queue, so this HTTP request never
    blocks on inference (see README "Асинхронная обработка").
    """
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status == JobStatus.processing:
        raise HTTPException(409, "Job is already processing")

    job.status = JobStatus.queued
    job.error = None
    session.add(job)
    session.commit()

    task_queue.enqueue("app.worker.tasks.run_job", job_id, job_id=f"job-{job_id}")
    return JobCreatedResponse(id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_status(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobStatusResponse.from_job(job)


@router.get("/{job_id}/anomalies", response_model=JobAnomaliesResponse)
def get_anomalies(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobAnomaliesResponse(id=job.id, bag_count=job.bag_count, anomalies=job.anomalies or [])


@router.get("/{job_id}/result")
def download_result(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.done or not job.output_path:
        raise HTTPException(409, "Result not ready yet")
    return FileResponse(
        job.output_path,
        media_type="video/mp4",
        filename=f"{job.original_filename}_processed.mp4",
    )


@router.get("", response_model=list[JobStatusResponse])
def list_jobs(session: Session = Depends(get_session)):
    jobs = session.exec(select(Job).order_by(Job.created_at.desc())).all()
    return [JobStatusResponse.from_job(j) for j in jobs]
