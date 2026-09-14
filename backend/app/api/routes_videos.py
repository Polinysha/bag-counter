import asyncio
import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.auth import require_api_key
from app.config import settings
from app.models import JobStatus
from app.repositories.job_repository import JobNotFoundError
from app.schemas import (
    JobAnomaliesResponse,
    JobCreatedResponse,
    JobStatusResponse,
    PaginatedJobsResponse,
)
from app.services.video_service import (
    InvalidUploadError,
    JobAlreadyProcessingError,
    ResultNotReadyError,
    UploadTooLargeServiceError,
    VideoService,
    build_video_service,
)

# dependencies=[...] applies require_api_key to every route on this
# router - see app/auth.py for what it checks and app/main.py for why
# GET /api/health is intentionally NOT behind this (it's outside this
# router, mounted separately, unauthenticated on purpose).
router = APIRouter(prefix="/videos", tags=["videos"], dependencies=[Depends(require_api_key)])


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


@router.get("/{job_id}/events")
async def stream_status(
    job_id: str,
    request: Request,
    service: VideoService = Depends(build_video_service),
):
    """
    Server-Sent Events alternative to polling GET /{job_id}: pushes a
    JobStatusResponse-shaped `data:` frame roughly every
    BC_SSE_POLL_INTERVAL_SECONDS, stopping once the job reaches a
    terminal status (done/failed) or the client disconnects.

    This is purely additive - GET /{job_id} still works exactly as
    before for anyone polling it - so there's nothing here for the v1
    compatibility checklist in docs/API_CONTRACTS.md to worry about.

    The DB read each tick still goes through the same synchronous
    VideoService/JobRepository as every other route (see README "Key
    Technical Decisions" - SQLite/SQLModel throughout); run_in_threadpool
    keeps that blocking call from stalling the event loop for every
    other request while this connection sits open.
    """
    try:
        await run_in_threadpool(service.get_status, job_id)
    except JobNotFoundError as exc:
        # Fail fast with a normal 404 rather than opening a stream that
        # would immediately have nothing to say.
        raise HTTPException(404, "Job not found") from exc

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                job = await run_in_threadpool(service.get_status, job_id)
            except JobNotFoundError:
                break
            payload = JobStatusResponse.from_job(job).model_dump(mode="json")
            yield f"data: {json.dumps(payload)}\n\n"
            if job.status in (JobStatus.done, JobStatus.failed):
                break
            await asyncio.sleep(settings.sse_poll_interval_seconds)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx (or any buffering reverse proxy) defaults to
            # buffering upstream responses, which would hold every SSE
            # frame until the connection closes - defeating the point.
            "X-Accel-Buffering": "no",
        },
    )


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


@router.get("", response_model=PaginatedJobsResponse)
def list_jobs(
    limit: int = Query(
        default=VideoService.DEFAULT_PAGE_SIZE,
        ge=1,
        le=VideoService.MAX_PAGE_SIZE,
        description="Max jobs to return.",
    ),
    offset: int = Query(default=0, ge=0, description="Jobs to skip, newest first."),
    service: VideoService = Depends(build_video_service),
):
    """
    Newest jobs first. See docs/API_CONTRACTS.md "GET /videos" - this
    endpoint's response was always documented as subject to change from
    a bare array to a paginated envelope, which is what this is.
    """
    page = service.list_jobs(limit=limit, offset=offset)
    return PaginatedJobsResponse(
        items=[JobStatusResponse.from_job(j) for j in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )
