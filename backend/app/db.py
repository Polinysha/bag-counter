from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def _engine_kwargs() -> dict:
    """
    SQLite needs check_same_thread=False: JobRepository (see
    app/repositories/job_repository.py) opens a fresh `Session(engine)`
    per call, and several routes invoke it via `run_in_threadpool` (the
    SSE endpoint's per-tick poll, for instance) - a different thread
    each time than whichever one first created the engine. Passing that
    same connect_arg to a Postgres/psycopg engine raises a TypeError
    (psycopg2/psycopg have no such parameter), so it's only applied
    when actually using SQLite.
    """
    if settings.database_url:
        return {}
    return {"connect_args": {"check_same_thread": False}}


engine = create_engine(settings.database_url or settings.sqlite_url, **_engine_kwargs())


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
