"""
Liveness/readiness checks for GET /api/health.

Kept as free functions (not a class) since each check is a single,
stateless, side-effect-free probe - there's no shared state or
lifecycle to justify a class here, unlike the service/repository
layers under app/services and app/repositories.
"""

from __future__ import annotations

from sqlmodel import Session, text

from app.db import engine
from app.worker.queue import TaskQueue


def check_db() -> bool:
    try:
        with Session(engine) as session:
            # session.execute() (not SQLModel's session.exec()) - exec()
            # is typed for SQLModel/SQLAlchemy Select objects only, a raw
            # text() probe like this one isn't a valid overload for it.
            session.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - a health check must never raise
        return False


def check_redis() -> bool:
    try:
        return bool(TaskQueue().redis_conn.ping())
    except Exception:  # noqa: BLE001 - a health check must never raise
        return False
