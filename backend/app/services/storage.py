"""File-storage side of a Job: where uploads and results live on disk."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}
DEFAULT_EXTENSION = ".mp4"


class StorageService:
    """Wraps `settings.uploads_dir` / `settings.processed_dir`. Kept as a
    thin class (rather than free functions) so it can be swapped for an
    object-storage-backed implementation (S3/GCS) later behind the same
    interface, and so it's trivially mockable in tests."""

    def save_upload(self, job_id: str, file: UploadFile) -> Path:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            ext = DEFAULT_EXTENSION
        dest = settings.uploads_dir / f"{job_id}{ext}"
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        return dest

    def output_path_for(self, job_id: str) -> Path:
        return settings.processed_dir / f"{job_id}_processed.mp4"


storage_service = StorageService()
