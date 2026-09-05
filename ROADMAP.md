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
- [ ] Swap SQLite -> Postgres (change `sqlite_url` in `config.py` to a
      `postgresql://` URL, add a `db` service to `docker-compose.yml`) -
      needed once this runs multi-instance rather than single-node.
- [ ] Replace status polling with Server-Sent Events / WebSocket on top
      of the same `Job` table (`GET /api/v1/videos/{id}` stays as a
      fallback).
- [ ] GPU image variant: CUDA torch wheel + `BC_MMDET_DEVICE=cuda:0`,
      published as a separate tag alongside the CPU image.
- [ ] CI: build & publish the full (non-lite) image on release tags,
      not just the lite sanity build used on every PR.

## API / product
- [ ] AuthN/authZ - currently anyone who can reach the API can upload
      and list all jobs; needed before this is exposed beyond a trusted
      network.
- [ ] Job retention / cleanup policy for `./data` (uploads + processed
      videos currently accumulate forever).
- [ ] Pagination for `GET /api/v1/videos` (currently returns every job).

## Tooling hardening
- [ ] Tighten `mypy` incrementally: `disallow_untyped_defs = true`
      module-by-module (see `[tool.mypy]` in `backend/pyproject.toml`),
      starting with `app/services` and `app/repositories`.
- [ ] Enforce Conventional Commits via a commit-msg hook (referenced as
      "preferred but not enforced" in `CONTRIBUTING.md`).
- [ ] Dependabot/renovate config for `requirements/*.txt` version bumps.

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
