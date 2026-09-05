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

## [Unreleased] - license & detector testability

### Added
- `LICENSE` (MIT) + README pointer - the repo was `Public` with no
  license, meaning nobody had explicit permission to use/fork it.
- `postprocess_detections()` extracted from `BagDetector.infer()`
  (app/worker/pipeline/detector.py) - the confidence/box-size filtering
  and label-index mapping is now a pure function, independent of the
  MMDetection model call. `BagDetector.infer()` itself is unchanged in
  behavior, just delegates to it.
- `tests/unit/test_detector.py` - 10 tests covering
  `postprocess_detections()` (score threshold, min/max area ratio,
  label mapping, edge cases) without needing MMDetection/torch
  installed. This was the one pipeline module with zero test coverage.

## [Unreleased] - production hardening

### Added
- `GET /api/health` now actually checks SQLite and Redis connectivity
  (`app/health.py`) and returns `503` with a `checks` breakdown when
  either is down, instead of unconditionally returning `200 {"status":
  "ok"}`.
- Upload size cap: `BC_MAX_UPLOAD_MB` (default 2048). Oversized uploads
  are rejected with `413` while streaming (not after being fully
  written to disk) and the `Job` is recorded as `failed` rather than
  silently dropped - see `StorageService.save_upload` /
  `VideoService.upload`.
- Frontend (`app/static/index.html`): every API call now goes through
  a wrapper that surfaces network/HTTP errors as a visible banner
  instead of throwing an uncaught rejection; status polling stops
  after repeated consecutive failures instead of polling forever
  against a dead server.
- `JobRepositoryProtocol` / `StorageServiceProtocol` / `TaskQueueProtocol`
  in `app/services/video_service.py` - `VideoService` now depends on
  structural types, so unit tests use plain in-memory fakes without
  subclassing the real repository/storage/queue classes.
- Unit tests: `tests/unit/test_storage.py` (upload size cap),
  `tests/unit/test_video_service.py` (orchestration logic).

## [1.0.0]
- Initial version: FastAPI + RQ/Redis + SQLite + MMDetection conveyor bag counter.
