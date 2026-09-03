import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class JobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)

    status: JobStatus = Field(default=JobStatus.queued)
    error: str | None = None

    original_filename: str
    input_path: str
    output_path: str | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    total_frames: int | None = None
    processed_frames: int = 0
    fps: float | None = None

    bag_count: int = 0

    # progress 0..100, cheap to poll from the API
    progress_pct: float = 0.0

    # list[dict] of anomaly events, see worker/pipeline/anomaly.py
    anomalies: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
