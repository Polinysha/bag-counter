from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from app.models import JobStatus


class JobCreatedResponse(BaseModel):
    id: str
    status: JobStatus


class AnomalyOut(BaseModel):
    frame: int
    timestamp_sec: float
    type: str
    severity: str
    message: str


class JobStatusResponse(BaseModel):
    id: str
    status: JobStatus
    error: Optional[str] = None
    original_filename: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    total_frames: Optional[int] = None
    processed_frames: int
    fps: Optional[float] = None
    progress_pct: float
    bag_count: int
    anomalies_count: int
    has_result: bool

    @classmethod
    def from_job(cls, job) -> "JobStatusResponse":
        return cls(
            id=job.id,
            status=job.status,
            error=job.error,
            original_filename=job.original_filename,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            total_frames=job.total_frames,
            processed_frames=job.processed_frames,
            fps=job.fps,
            progress_pct=job.progress_pct,
            bag_count=job.bag_count,
            anomalies_count=len(job.anomalies or []),
            has_result=bool(job.output_path),
        )


class JobAnomaliesResponse(BaseModel):
    id: str
    bag_count: int
    anomalies: List[AnomalyOut]
