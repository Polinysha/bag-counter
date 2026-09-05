# Conveyor Belt Bag Counter

A web application for processing conveyor belt footage: bag detection (MMDetection),
inter-frame tracking, counting bags that pass through, result visualization on
video, asynchronous background processing, and monitoring of anomalies that could
affect counting accuracy.

## Quick Start

Requirements: Docker + Docker Compose (the `docker compose` plugin, v2).

```bash
git clone <repo-url> bag-counter
cd bag-counter
docker compose up --build
```

The first build takes a few minutes — it downloads PyTorch (CPU build) and the
MMDetection model weights (see `backend/Dockerfile`). Once it's up:

* UI: http://localhost:8000
* Swagger / OpenAPI: http://localhost:8000/docs

In the UI: select `input.mp4` -> "Upload and process" -> wait for progress ->
download the processed video and view the anomaly log.

Via the API (curl):

```bash
# 1. upload the video
curl -F "file=@input.mp4" http://localhost:8000/api/v1/videos
# -> {"id": "<job_id>", "status": "queued"}

# 2. start processing (does not block the request)
curl -X POST http://localhost:8000/api/v1/videos/<job_id>/process

# 3. poll status
curl http://localhost:8000/api/v1/videos/<job_id>

# 4. download the result once status == "done"
curl -OJ http://localhost:8000/api/v1/videos/<job_id>/result

# 5. list anomalies
curl http://localhost:8000/api/v1/videos/<job_id>/anomalies
```

All uploaded and processed videos, as well as the job database (SQLite), are
stored in `./data` on the host (see `docker-compose.yml`) — this is a bind
mount, not a volume internal to the container, so recreating containers
(`docker compose up --build`, `docker compose down` without `-v`) does not
delete them.

By default inference runs on CPU (`MMDET_DEVICE=cpu` in `.env` /
`.env.example`). For GPU: build the image with a CUDA-enabled torch wheel and
set `MMDET_DEVICE=cuda:0` — details are in the comments in
`backend/Dockerfile` and `docker-compose.yml`.

## Architecture

```
                 ┌────────────┐        ┌───────────┐
   POST /videos  │            │ enqueue│           │
  ──────────────►│  FastAPI   ├───────►│   Redis   │
   POST .../process           │        │  (queue)  │
  ◄────────────── │  (api)    │        │           │
   202 + job_id    └─────┬─────┘        └─────┬─────┘
                          │ SQLite (job status,      │ consume
                          │ progress, counter,       ▼
                          │ anomalies)         ┌─────────────┐
                          └───────────────────►│  RQ worker  │
                                                │  (worker)   │
                          ┌─────────────────────┤             │
                          │  ./data (bind mount) │ MMDetection │
                          │  uploads/ processed/ │ + tracker + │
                          │  db/app.db           │ counter +   │
                          └─────────────────────►│ anomaly-mon.│
                                                 └─────────────┘
```

Three containers (`docker-compose.yml`):

* **redis** — the task queue broker.
* **api** — the FastAPI application: accepts videos, enqueues processing jobs,
  serves status/results. Does not run inference itself.
* **worker** — an `rq worker` process that pulls jobs off the queue and runs
  the whole CV pipeline. Uses the same Docker image as `api` (see
  `backend/Dockerfile`), just with a different startup command — this
  guarantees the detector code in `api` and `worker` never drifts apart, and
  lets workers be scaled independently of the API (`docker compose up
  --scale worker=3`).

### Approach to Counting Bags

1. **Detection** (`app/worker/pipeline/detector.py`) — on every frame the
   MMDetection model (RTMDet-tiny, COCO-pretrained, by default) returns boxes
   with classes and scores. The task did not come with a labeled dataset of
   bags specific to this conveyor, so instead of fine-tuning the model for a
   single "bag" class (which would require labeling that doesn't exist), a
   deliberate trade-off was made: detections are filtered not by COCO class
   name (bags aren't labeled there as such), but *geometrically* — by whether
   the box center falls inside the conveyor's ROI polygon and by a reasonable
   box-area range relative to the frame (`min/max_box_area_ratio` in
   `config.py`). MMDetection is thus used as a general-purpose object detector
   in a scene where the only moving objects inside the ROI are bags. This is a
   deliberate limitation of the chosen approach given the constraints of the
   task; swapping in a fine-tuned single-class checkpoint is a change to two
   paths in `config.py` (`BC_MMDET_CONFIG` / `BC_MMDET_CHECKPOINT`), with no
   changes needed elsewhere in the pipeline.

2. **Tracking** (`app/worker/pipeline/tracker.py`) — a lightweight tracker in
   the spirit of SORT: matching boxes across frames by IoU via the Hungarian
   algorithm (`scipy.optimize.linear_sum_assignment`), with constant-velocity
   position prediction for frames where detection was missed. Each track gets
   a stable `track_id` and keeps a history of centroids. A track is considered
   confirmed (`confirmed`) after `tracker_min_hits` consecutive matches — this
   filters out isolated false detector triggers from real bags.

3. **Counting** (`app/worker/pipeline/counter.py`) — a bag is counted exactly
   once, the moment the segment between a track's last two centroid positions
   crosses the configured counting line (`counting_line` in `config.py`) in
   the belt's direction of travel. The `counted` flag on the track is the
   single source of truth: even if the box keeps "touching" the line for a few
   more frames, it won't be incremented again. A track can go unmatched for
   1-2 frames (partial occlusion, a dip in score) and still be counted, as
   long as `tracker_max_age` isn't exceeded — that's what protects against
   double-counting or losing the count between frames.

The ROI polygon and counting line are given in normalized coordinates (0..1),
tuned to the geometry of `input.mp4` (the belt runs diagonally from the tunnel
toward the camera) and are resolution-independent — see `SceneGeometry` in
`app/worker/pipeline/roi.py`.

### Asynchronous Processing

`POST /api/v1/videos` only saves the file and creates a `Job(status=queued)`
record — this is fast regardless of video length. `POST
/api/v1/videos/{id}/process` puts the job on the Redis queue (`rq.Queue.enqueue`)
and returns immediately: the HTTP request itself never waits for inference to
finish. The actual processing (reading the video, per-frame detection,
tracking, writing the output video) runs in a separate `rq worker` process,
which writes progress (`processed_frames`, `progress_pct`) to the DB every 10
frames — so the frontend can poll status without long-running requests. If a
job fails (`try/except` in `worker/tasks.py`), the status becomes `failed`
with the error text available via `GET /api/v1/videos/{id}`.

### Anomaly Monitoring

What counts as an anomaly was explicitly left up to the candidate. The signals
chosen are ones that specifically threaten *counting accuracy* (rather than
any general video-quality issue) — implemented in
`app/worker/pipeline/anomaly.py`:

| Type | Triggered when | What it may indicate |
|---|---|---|
| `stall` | no detections in the ROI for longer than `anomaly_stall_seconds`, after bags had already been flowing | the belt stopped / the camera view is blocked |
| `unusual_size` | a counted bag's box area deviates strongly from the median of the last 50 | two bags merged into one detection, or a false positive |
| `possible_double_count` | two line crossings happen closer together than `anomaly_double_count_seconds` | a tracker ID switch, or one bag split into two detections |
| `lost_near_line` | a confirmed but not-yet-counted track disappears near the counting line | likely a missed bag (undercount) |
| `low_confidence` | average detection confidence over a rolling window drops below the threshold | glare/blur/lighting issue — counts in this window should be trusted less |

Each anomaly is a `{frame, timestamp_sec, type, severity, message}` record,
written to the `Job.anomalies` JSON column (see `models.py`) and served via
`GET /api/v1/videos/{id}/anomalies`. The most recent active anomaly is also
drawn as a red banner at the bottom of the frame in the output video
(`_draw_anomaly_banner` in `video_processor.py`), so it's visible directly
while watching the result, not only in the log.

### Video Storage

`./data` on the host is mounted as a bind mount into `/data` inside `api` and
`worker` (`docker-compose.yml`). Inside it: `uploads/` (source files),
`processed/` (results), and `db/app.db` (SQLite with job records). The path is
configurable via `BC_DATA_DIR`; to move it to a separate disk/partition, just
change `./data` to the desired path in `docker-compose.yml`.

## Key Technical Decisions and Rationale

* **FastAPI + RQ/Redis instead of Celery** — for a single queue with one type
  of heavy task (video), RQ is simpler to operate and configure than Celery,
  and survives container recreation just as well (jobs live in Redis, status
  lives in SQLite on a volume). Celery is justified when you need multiple
  queues/task routing by type, which isn't needed here.
* **SQLite instead of Postgres** — for a single-user/single-instance test
  task, an extra DB service brings no architectural benefit, and SQLite on a
  volume already provides persistence across container recreation. Switching
  to Postgres is a change to `sqlite_url` in `config.py` to a
  `postgresql://...` URL plus adding a service to `docker-compose.yml`; the
  rest of the code (SQLModel) doesn't change.
* **A single Docker image for both `api` and `worker`** — eliminates any
  version drift between the process accepting requests and the process
  actually counting bags.
* **RTMDet-tiny (CPU) by default** — a trade-off between out-of-the-box
  detection quality and the requirement that the task build and run without a
  GPU on the reviewer's machine. All detector/tracker/counting-line parameters
  live in `app/config.py` and are read from environment variables (`BC_*` in
  `docker-compose.yml` / `.env`), so switching models, adjusting the ROI for a
  different camera, or tuning thresholds requires no code changes.
* **A lightweight IoU-based SORT-style tracker rather than heavy Re-ID** — the
  scene is simple (a single lane, bags barely occlude each other), so IoU +
  Hungarian matching gives stable IDs at a much lower cost than adding a
  re-identification network, and fits comfortably within a CPU budget.

## Repository Structure

```
backend/
  app/
    api/routes_videos.py         # HTTP endpoints (thin: parse request -> VideoService -> HTTP response)
    services/
      video_service.py           # use-case orchestration for the API (upload / start / status / result)
      storage.py                 # StorageService: upload/result file paths on disk
    repositories/
      job_repository.py          # JobRepository: the only module that queries the Job table
    worker/
      queue.py                   # TaskQueue: RQ connection + enqueue
      tasks.py                   # RQ entrypoint (dotted-path adapter, see file docstring)
      job_runner.py               # JobRunner: orchestrates one job (status transitions + pipeline call)
      pipeline/                   # pure CV pipeline, no DB/HTTP/queue knowledge
        detector.py                # MMDetection wrapper (+ motion-based MockDetector fallback)
        tracker.py                  # SORT-lite tracker
        roi.py                       # ROI polygon / counting line geometry
        counter.py                    # line-crossing counting logic
        anomaly.py                     # anomaly monitoring
        video_processor.py              # pipeline glue + frame rendering
    models.py / schemas.py / db.py / config.py / main.py
    static/index.html            # minimal UI
  requirements/
    base.txt                     # FastAPI/RQ/SQLModel core - always installed
    cv.txt                       # opencv/numpy/scipy - always installed (tracker/roi/counter/anomaly need these, not MMDetection)
    ml.txt                       # pinned version record for the MMDetection/torch stack (installed via `mim` in Dockerfile, not pip -r)
    dev.txt                      # ruff/mypy/pytest/pre-commit - dev & CI only, never in the runtime image
  tests/
    unit/                        # pure-logic tests: roi/counter/tracker/anomaly, no Docker/Redis/MMDetection needed
    integration/                 # API tests against the FastAPI app with a fake VideoService/queue
  Dockerfile                     # single image for api+worker; ARG SKIP_ML_STACK for a lite/CI build
  pyproject.toml                 # ruff + mypy + pytest config
docker-compose.yml
docker-compose.ci.yml            # lite-image override used by CI (see .github/workflows/ci.yml)
.env.example
docs/API_CONTRACTS.md            # versioned REST contract, error shape, compatibility policy
CONTRIBUTING.md                  # branching model, commit convention, how to open a PR
ROADMAP.md                       # backlog, meant to be mirrored 1:1 into GitHub Issues (see scripts/create_issues.sh)
data/                            # bind-mount volume (empty in the repository)
```

## Development Tooling

* **Lint / format**: [ruff](https://docs.astral.sh/ruff/) (`make lint`, `make format`). Config in `backend/pyproject.toml`.
* **Types**: mypy in non-strict-but-real mode (`make typecheck`) - see `[tool.mypy]` in `pyproject.toml` for what's excluded and why (mainly the untyped `mmdet`/`cv2` stubs).
* **Tests**: pytest (`make test`). Unit tests never require Docker, Redis, or the MMDetection weights - they run against `tracker/roi/counter/anomaly` directly and against the API with `VideoService`/`TaskQueue` faked out.
* **Pre-commit**: `pre-commit install` runs ruff (lint+format) and a requirements-sync check on every commit; the same checks run in CI so a bypassed hook still gets caught.
* **Lite Docker image**: `docker build --build-arg SKIP_ML_STACK=true backend` skips the torch/MMDetection install entirely (`BagDetector` becomes unavailable, `MockDetector` is used automatically, see `app/worker/pipeline/detector.py::build_detector`). This is what CI builds; the default (`SKIP_ML_STACK=false`, i.e. plain `docker compose up --build`) always includes the full ML stack.

## API Contracts

The full REST contract (resources, request/response schemas, status codes, the versioning and backward-compatibility policy) is specified in [`docs/API_CONTRACTS.md`](docs/API_CONTRACTS.md) and enforced at runtime by the Pydantic models in `app/schemas.py`. The live interactive contract is always at `/docs` (Swagger) / `/openapi.json`. All endpoints are versioned under `/api/v1`.

## Contributing / Branching Model

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the `main` / `dev` / `feature/*` branching model, commit conventions, and how PRs are expected to flow. Planned follow-up work is tracked in [`ROADMAP.md`](ROADMAP.md), mirrored into GitHub Issues.

## Known Limitations / Further Improvements

* The detector is used in class-agnostic mode on top of a COCO pretrain (see
  "Approach to Counting Bags") — for production, an MMDetection model should
  be fine-tuned on labeled frames from this specific conveyor, which would
  improve both counting accuracy and some anomaly signals (`unusual_size`,
  `low_confidence`).
* Progress is served via polling; this can easily be swapped for
  Server-Sent Events / WebSocket on top of the same `Job` table.
* A single worker by default — to process multiple videos in parallel:
  `docker compose up --scale worker=N`.

## License

MIT — see [LICENSE](LICENSE).
