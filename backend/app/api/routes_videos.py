from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.repositories.job_repository import JobNotFoundError
from app.schemas import JobAnomaliesResponse, JobCreatedResponse, JobStatusResponse
from app.services.video_service import (
    InvalidUploadError,
    JobAlreadyProcessingError,
    ResultNotReadyError,
    UploadTooLargeServiceError,
    VideoService,
    build_video_service,
)

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("", response_model=JobCreatedResponse, status_code=201)
def upload_video(
    file: UploadFile = File(...),
    service: VideoService = Depends(build_video_service),
):
    """
    Upload a video. This only stores the file and creates a job record
    - it does NOT start processing (see POST /videos/{id}/process),
    so the upload itself is always fast regardless of video length.
    """
    try:
        job = service.upload(file)
    except UploadTooLargeServiceError as exc:
        # must be checked before InvalidUploadError - it's a subclass
        raise HTTPException(413, str(exc)) from exc
    except InvalidUploadError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JobCreatedResponse(id=job.id, status=job.status)


@router.post("/{job_id}/process", response_model=JobCreatedResponse)
def start_processing(job_id: str, service: VideoService = Depends(build_video_service)):
    """
    Enqueue the video for background processing and return immediately.
    The actual MMDetection inference happens in a separate worker
    process consuming the Redis queue, so this HTTP request never
    blocks on inference (see README "Asynchronous Processing").
    """
    try:
        job = service.start_processing(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(404, "Job not found") from exc
    except JobAlreadyProcessingError as exc:
        raise HTTPException(409, str(exc)) from exc
    return JobCreatedResponse(id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_status(job_id: str, service: VideoService = Depends(build_video_service)):
    try:
        job = service.get_status(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(404, "Job not found") from exc
    return JobStatusResponse.from_job(job)


@router.get("/{job_id}/anomalies", response_model=JobAnomaliesResponse)
def get_anomalies(job_id: str, service: VideoService = Depends(build_video_service)):
    try:
        job = service.get_anomalies(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(404, "Job not found") from exc
    # job.anomalies is list[dict] (JSON column, see models.py); pydantic
    # validates/coerces each dict into AnomalyOut at construction time -
    # mypy can't see that runtime coercion, hence the ignore.
    return JobAnomaliesResponse(
        id=job.id,
        bag_count=job.bag_count,
        anomalies=job.anomalies or [],  # type: ignore[arg-type]
    )


@router.get("/{job_id}/result")
def download_result(job_id: str, service: VideoService = Depends(build_video_service)):
    try:
        job, output_path = service.get_result_path(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(404, "Job not found") from exc
    except ResultNotReadyError as exc:
        raise HTTPException(409, str(exc)) from exc
    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"{job.original_filename}_processed.mp4",
    )


@router.get("", response_model=list[JobStatusResponse])
def list_jobs(service: VideoService = Depends(build_video_service)):
    jobs = service.list_jobs()
    return [JobStatusResponse.from_job(j) for j in jobs]
