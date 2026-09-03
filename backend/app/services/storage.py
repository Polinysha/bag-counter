import shutil
import uuid
from pathlib import Path
from fastapi import UploadFile

from app.config import settings

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}


def save_upload(job_id: str, file: UploadFile) -> Path:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".mp4"
    dest = settings.uploads_dir / f"{job_id}{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return dest


def output_path_for(job_id: str) -> Path:
    return settings.processed_dir / f"{job_id}_processed.mp4"
