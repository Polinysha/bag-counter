"""File-storage side of a Job: where uploads and results live on disk."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.config import settings

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}
DEFAULT_EXTENSION = ".mp4"

# Read/write in chunks rather than shutil.copyfileobj's default 64 KiB so
# the size cap below can be enforced *while* streaming, instead of only
# after the whole file - a 50 GiB upload gets rejected after ~1 MiB
# written, not after it's already filled the disk.
_CHUNK_SIZE = 1024 * 1024  # 1 MiB


class UploadTooLargeError(ValueError):
    def __init__(self, max_mb: int):
        super().__init__(f"Upload exceeds the {max_mb} MiB limit")
        self.max_mb = max_mb


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
        max_bytes = settings.max_upload_mb * 1024 * 1024

        written = 0
        try:
            with dest.open("wb") as out:
                while chunk := file.file.read(_CHUNK_SIZE):
                    written += len(chunk)
                    if written > max_bytes:
                        raise UploadTooLargeError(settings.max_upload_mb)
                    out.write(chunk)
        except UploadTooLargeError:
            dest.unlink(missing_ok=True)  # don't leave a truncated file behind
            raise
        return dest

    def output_path_for(self, job_id: str) -> Path:
        return settings.processed_dir / f"{job_id}_processed.mp4"


storage_service = StorageService()
