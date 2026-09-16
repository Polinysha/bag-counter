# Roadmap / Backlog

Each item below is meant to become one GitHub Issue (see
`scripts/create_issues.sh`) and be closed by a PR from a
`feature/<name>` branch into `dev` (see `CONTRIBUTING.md`). Check items
off here as their issue closes.

## Testing
- [ ] `BagDetector.infer()` itself (the MMDetection call, not just the
      `postprocess_detections()` logic it wraps - see
      `tests/unit/test_detector.py`) still has no automated test: doing
      so needs either a tiny real checkpoint fixture or a mocked
      `inference_detector` return shape, and isn't free to set up. Low
      priority since `postprocess_detections` - the part actually at
      risk of a silent regression (thresholds, label mapping) - is
      covered.

## Detection & counting accuracy
- [ ] Fine-tune an MMDetection checkpoint on labeled frames from this
      conveyor instead of the class-agnostic COCO-pretrained detector
      (`BC_MMDET_CONFIG` / `BC_MMDET_CHECKPOINT` swap, see README
      "Approach to Counting Bags"). Should improve `unusual_size` and
      `low_confidence` anomaly precision too.
- [ ] Re-validate `roi_polygon` / `counting_line` calibration for camera
      angles other than the supplied `input.mp4`.

## Scalability / infra
- [x] Swap SQLite -> Postgres, needed once this runs multi-instance
      rather than single-node. Implemented as an opt-in swap, not a
      replacement: set `BC_DATABASE_URL` (see `app/config.py`) and run
      with `docker-compose.postgres.yml` - SQLite stays the zero-config
      default for plain `docker compose up`. Verified against a real
      PostgreSQL 16 instance (table creation, full JobRepository
      round-trip) during development, not just unit-tested against the
      URL-selection logic - see CHANGELOG.md.
- [x] Replace status polling with Server-Sent Events / WebSocket on top
      of the same `Job` table (`GET /api/v1/videos/{id}` stays as a
      fallback). Implemented as SSE (`GET /{id}/events`, see
      docs/API_CONTRACTS.md) rather than WebSocket - status is
      one-directional server -> client, so SSE's simpler HTTP-based
      model fits without the added complexity a full-duplex WebSocket
      would add for no benefit here. The frontend (`static/index.html`)
      uses it by default and falls back to the original polling loop
      if the stream can't be opened or breaks mid-way.
- [ ] GPU image variant: CUDA torch wheel + `BC_MMDET_DEVICE=cuda:0`,
      published as a separate tag alongside the CPU image.
- [x] CI: build & publish the full (non-lite) image on release tags,
      not just the lite sanity build used on every PR -
      `.github/workflows/release.yml`, triggered on `v*.*.*` tags,
      pushes to `ghcr.io/polinysha/bag-counter`. See README "Published
      image" and CONTRIBUTING.md step 6.

## API / product
- [x] AuthN/authZ - shared-secret `X-API-Key` auth (`app/auth.py`,
      `BC_API_KEY`), see README "Security". Deliberately not per-user
      accounts/RBAC - single-tenant tool, see the module's docstring
      for the reasoning; revisit only if that assumption changes.
- [ ] Job retention / cleanup policy for `./data` (uploads + processed
      videos currently accumulate forever).
- [x] Pagination for `GET /api/v1/videos` - `?limit=&offset=` query
      params, response wrapped in `{items, total, limit, offset}`. See
      docs/API_CONTRACTS.md for why this shape change doesn't count as
      a `v1` break (the endpoint was always documented as subject to it).

## Tooling hardening
- [x] Tighten `mypy` incrementally: `disallow_untyped_defs = true`
      module-by-module (see `[tool.mypy]` in `backend/pyproject.toml`).
      Done for `app/services` and `app/repositories` - both were
      already fully annotated except one Protocol method, so this
      mostly just locks in what was already true and prevents drift.
      Next candidates: `app/api`, `app/worker` (excluding `pipeline/`,
      which touches untyped cv2/mmdet APIs at the boundary and isn't
      worth fighting).
- [x] Enforce Conventional Commits via a commit-msg hook - local
      enforcement via `.pre-commit-config.yaml`'s
      `conventional-pre-commit` hook (needs `pre-commit install`, now
      installed for both `pre-commit` and `commit-msg` stages by
      default - see `default_install_hook_types`), backstopped by
      `.github/workflows/ci.yml`'s `commit-messages` job for any
      commit made with `--no-verify`. Merge commits are exempt.
- [x] Dependabot config - `.github/dependabot.yml` covers
      `requirements/*.txt` (pip), `backend/Dockerfile`'s base image
      (docker), and `.github/workflows/*.yml` action versions
      (github-actions). `requirements/ml.txt` is documentation-only
      (see its header comment) and has nothing for Dependabot to bump;
      keep it in sync with `backend/Dockerfile`'s ARGs by hand.

## Explicitly out of scope for this project
This is a computer-vision pipeline (detection -> tracking -> counting)
with no text/LLM component and no document ingestion, so two items from
the original task checklist don't apply here and are intentionally not
present:
- a separate "LLM calls" module / pipeline - there is no LLM in this
  system, nothing calls a language model anywhere in `backend/app`;
- a "chunking" module - chunking is a text/RAG-ingestion concept and has
  no equivalent in a frame-by-frame video pipeline (the nearest analog,
  per-frame processing, already lives in `video_processor.py` and isn't
  a separate concern worth extracting).
If a future requirement actually introduces an LLM-backed feature (e.g.
an anomaly-report summarizer), it should get its own `app/llm/` package
(client wrapper + prompt templates) and its own `app/pipelines/`-style
orchestration module, mirroring how `worker/pipeline/` is isolated from
`worker/job_runner.py` today - but that's premature until such a feature
is actually planned.
