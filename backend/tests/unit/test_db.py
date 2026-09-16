"""
Unit tests for app/db.py's engine-selection logic. Deliberately does
NOT connect to a real database - CI and local `pytest` runs have no
Postgres available, and shouldn't need one. The Postgres path itself
was verified manually against a real PostgreSQL 16 instance (create
tables, JobRepository create/get/mark_queued/list_page round-trip) -
see the "Postgres support" entry in CHANGELOG.md.
"""

from app.config import settings
from app.db import _engine_kwargs


def test_sqlite_path_needs_check_same_thread_false(monkeypatch):
    monkeypatch.setattr(settings, "database_url", None)
    assert _engine_kwargs() == {"connect_args": {"check_same_thread": False}}


def test_postgres_path_has_no_sqlite_only_connect_args(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://user:pass@host:5432/db")
    assert _engine_kwargs() == {}
