import enum
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, JSON
from sqlmodel import SQLModel, Field


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)

    status: JobStatus = Field(default=JobStatus.queued)
    error: Optional[str] = None

    original_filename: str
    input_path: str
    output_path: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    total_frames: Optional[int] = None
    processed_frames: int = 0
    fps: Optional[float] = None

    bag_count: int = 0

    # progress 0..100, cheap to poll from the API
    progress_pct: float = 0.0

    # list[dict] of anomaly events, see worker/pipeline/anomaly.py
    anomalies: List[dict] = Field(default_factory=list, sa_column=Column(JSON))
