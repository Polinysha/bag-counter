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

## [Unreleased] - mypy: disallow_untyped_defs for services/repositories

### Changed
- `backend/pyproject.toml`: added a `[[tool.mypy.overrides]]` block
  enabling `disallow_untyped_defs = true` for `app.services.*` and
  `app.repositories.*` - every function in these packages now needs a
  full signature (return type included), not just some parameters
  annotated. The rest of the codebase keeps the looser global default
  for now; see ROADMAP.md "Tooling hardening" for the next candidates.
- `app/services/video_service.py`: `StorageServiceProtocol.save_upload`
  was missing a return type annotation (`-> Path`) - the one thing
  this override actually caught, since both packages were already
  otherwise fully typed.

## [Unreleased] - publish full image on release tags

### Added
- `.github/workflows/release.yml`: on every `v*.*.*` tag push, builds
  the FULL image (`SKIP_ML_STACK=false` - the actual MMDetection/torch
  stack, not the lite/CI sanity-build image) and pushes it to GitHub
  Container Registry as `ghcr.io/polinysha/bag-counter:<version>`,
  `:<major>.<minor>`, and `:latest`. Uses the built-in `GITHUB_TOKEN`
  (no extra secrets to configure) and the GitHub Actions build cache.
- README "Published image" section (how to `docker pull` it, and the
  one-time step to make the GHCR package public after the first
  release).
- CONTRIBUTING.md step 6: tag only after confirming the `dev -> main`
  merge commit is actually on `main`, since tagging the wrong commit
  publishes a release image that doesn't match the tag.

## [Unreleased] - pagination for GET /videos

### Changed
- `GET /api/v1/videos` now takes `?limit=<1-200, default 50>&offset=`
  and returns `{items, total, limit, offset}` instead of a bare
  `JobStatusResponse[]` array. See docs/API_CONTRACTS.md for why this
  is not treated as a `v1` compatibility break (the endpoint was
  always documented as "unpaginated today ... do not build clients
  that assume this stays unpaginated").
- `JobRepository.list_all()` replaced by `list_page(limit, offset)`,
  returning a `JobPage(items, total)`. `VideoService.list_jobs()` now
  validates `limit`/`offset` itself (not just at the FastAPI `Query()`
  layer), since it's meant to be callable from non-HTTP contexts too.

### Added
- 9 new tests: `tests/unit/test_video_service.py` (page slicing, total
  count, offset-beyond-total, limit/offset validation), 4 new
  integration tests on the real route (envelope shape, defaults, 422
  on out-of-range params).

## [Unreleased] - API-key authentication

### Added
- `app/auth.py`: shared-secret `X-API-Key` auth for every `/api/v1/*`
  route, gated by `BC_API_KEY` (open/unauthenticated mode when unset,
  which is the default and logs a startup warning). Constant-time
  comparison via `hmac.compare_digest`.
- Frontend: API-key input field (session-only storage), sent as
  `X-API-Key` on every request; downloading the processed video now
  goes through `fetch()` + a Blob URL when a key is set, since a plain
  `<a href>` can't attach a custom header.
- `docs/API_CONTRACTS.md`, README "Security" section, `.env.example`,
  `docker-compose.yml` updated to document/wire `BC_API_KEY`.
- Tests: `tests/unit/test_auth.py` (dependency logic), 4 new
  integration tests (open mode, missing/wrong/correct key, health
  endpoint staying unauthenticated).

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
