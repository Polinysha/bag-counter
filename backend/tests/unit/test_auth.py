"""Unit tests for require_api_key (app/auth.py)."""

import pytest
from fastapi import HTTPException

from app.auth import require_api_key
from app.config import settings


def test_open_mode_allows_any_request_when_no_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "api_key", None)
    # should not raise, regardless of header presence
    require_api_key(x_api_key=None)
    require_api_key(x_api_key="anything")


def test_missing_header_rejected_when_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "expected-secret")
    with pytest.raises(HTTPException) as exc_info:
        require_api_key(x_api_key=None)
    assert exc_info.value.status_code == 401


def test_wrong_key_rejected(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "expected-secret")
    with pytest.raises(HTTPException) as exc_info:
        require_api_key(x_api_key="wrong-secret")
    assert exc_info.value.status_code == 401


def test_correct_key_accepted(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "expected-secret")
    require_api_key(x_api_key="expected-secret")  # should not raise
