# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Service/repository layering (`VideoService`, `JobRepository`, `TaskQueue`, `StorageService`)
  so routes and the worker task no longer touch `Session`/`Queue` directly.
- `/api/v1` prefix and a dedicated `/api/health` liveness endpoint.
- `docs/API_CONTRACTS.md` as the source-of-truth REST contract.
- Split `requirements/` (`base` / `cv` / `ml` / `dev`) and a `SKIP_ML_STACK`
  Docker build arg for a lite image used by CI and non-CV local dev.
- ruff + mypy + pytest tooling, pre-commit hooks, `Makefile`, GitHub Actions CI.
- Unit tests for `roi` / `counter` / `tracker` / `anomaly`; integration tests
  for the `/api/v1/videos` routes against a faked `VideoService`.
- `CONTRIBUTING.md`, `ROADMAP.md`, issue/PR templates.

### Changed
- `main.py` moved from `@app.on_event("startup")` to a `lifespan` context manager.

## [1.0.0]
- Initial version: FastAPI + RQ/Redis + SQLite + MMDetection conveyor bag counter.
