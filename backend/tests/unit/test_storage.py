"""Unit tests for StorageService (app/services/storage.py), focused on
the upload-size cap since that's the one piece of real logic here -
the rest is thin path-joining."""

import io

import pytest
from fastapi import UploadFile

from app.config import settings
from app.services.storage import StorageService, UploadTooLargeError


def _upload_file(data: bytes, filename: str = "clip.mp4") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


def test_save_upload_within_limit_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    storage = StorageService()
    dest = storage.save_upload("job-1", _upload_file(b"x" * 100))

    assert dest.exists()
    assert dest.read_bytes() == b"x" * 100


def test_save_upload_over_limit_raises_and_removes_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # 1 MiB chunks are read at a time (see storage.py _CHUNK_SIZE) so use
    # a limit smaller than one chunk to trigger the cap deterministically
    # without needing a multi-MB fixture.
    monkeypatch.setattr(settings, "max_upload_mb", 0)  # 0 MiB = 0 bytes allowed

    storage = StorageService()
    with pytest.raises(UploadTooLargeError):
        storage.save_upload("job-2", _upload_file(b"x" * 10))

    assert not (tmp_path / "uploads" / "job-2.mp4").exists()


def test_unrecognized_extension_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "max_upload_mb", 10)

    storage = StorageService()
    dest = storage.save_upload("job-3", _upload_file(b"data", filename="clip.weird"))

    assert dest.suffix == ".mp4"
