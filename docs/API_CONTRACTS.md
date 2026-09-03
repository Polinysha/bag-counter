# API Contracts

Source of truth for the HTTP contract. The live, always-accurate version
of the same information is the generated OpenAPI schema at `/openapi.json`
(Swagger UI at `/docs`) - this document is the human-readable companion
that also states the *policy* decisions the schema alone can't express
(versioning, compatibility, error shape).

## Versioning

All business endpoints are namespaced under `/api/v1`. `/api/health` is
deliberately outside the version prefix - it's infrastructure (liveness
probe), not part of the versioned business contract, and load balancers
/ orchestrators should never need to know the API version to check it.

**Policy**: `v1` is additive-only (new optional fields, new endpoints).
Any breaking change (removing/renaming a field, changing a status code's
meaning, changing required-ness) ships as `/api/v2` with `v1` kept
running until clients migrate - never a silent breaking change to `v1`.

## Resources

### `Job`

The one resource in the system. Created by an upload, transitions through
`queued -> processing -> done | failed`.

```
JobStatus = "queued" | "processing" | "done" | "failed"
```

### `POST /api/v1/videos`

Upload a video and create a `Job`. Does **not** start processing.

* Request: `multipart/form-data`, field `file` (`.mp4`/`.avi`/`.mov`/`.mkv`;
  unrecognized extensions are stored as `.mp4`).
* Response `201`:
  ```json
  { "id": "string", "status": "queued" }
  ```
* Errors: `400` if `file` has no filename.

### `POST /api/v1/videos/{job_id}/process`

Enqueue the job for background processing. Returns immediately - inference
runs in the `worker` process, not on this request.

* Response `200`: same shape as upload (`id`, `status`).
* Errors: `404` unknown `job_id`; `409` if the job is already `processing`.

### `GET /api/v1/videos/{job_id}`

Poll job status/progress.

* Response `200`:
  ```json
  {
    "id": "string",
    "status": "queued|processing|done|failed",
    "error": "string | null",
    "original_filename": "string",
    "created_at": "2026-01-01T00:00:00",
    "started_at": "2026-01-01T00:00:00 | null",
    "finished_at": "2026-01-01T00:00:00 | null",
    "total_frames": "int | null",
    "processed_frames": "int",
    "fps": "float | null",
    "progress_pct": "float (0-100)",
    "bag_count": "int",
    "anomalies_count": "int",
    "has_result": "bool"
  }
  ```
* Errors: `404` unknown `job_id`.

### `GET /api/v1/videos/{job_id}/anomalies`

* Response `200`:
  ```json
  {
    "id": "string",
    "bag_count": "int",
    "anomalies": [
      {
        "frame": "int",
        "timestamp_sec": "float",
        "type": "stall|unusual_size|possible_double_count|lost_near_line|low_confidence",
        "severity": "info|warning|critical",
        "message": "string"
      }
    ]
  }
  ```
* Errors: `404` unknown `job_id`.

### `GET /api/v1/videos/{job_id}/result`

Downloads the processed video (`video/mp4`).

* Errors: `404` unknown `job_id`; `409` if `status != done`.

### `GET /api/v1/videos`

Lists all jobs, newest first. **Unpaginated today** - see
`ROADMAP.md` "Paginate GET /api/v1/videos"; do not build clients that
assume this stays unpaginated.

* Response `200`: `JobStatusResponse[]` (same shape as the single-job GET).

### `GET /api/health`

* Response `200`: `{ "status": "ok" }`. No auth, no versioning - pure
  liveness probe for orchestrators/load balancers.

## Error shape

All error responses use FastAPI's default `HTTPException` shape:

```json
{ "detail": "human-readable message" }
```

`detail` is not machine-parsed by any current client - if a caller needs
to branch on error *type* rather than just the HTTP status code, that's a
`v2` concern (structured `{ "error_code": ..., "detail": ... }`), tracked
informally; open an issue if you need it sooner.

## Backward compatibility checklist for a `v1` PR

Before merging a PR that touches `app/api/routes_videos.py` or
`app/schemas.py`, confirm:
- [ ] No existing field removed or renamed.
- [ ] No existing field's type narrowed or made required-where-optional.
- [ ] No status code for an existing situation changed.
- [ ] New optional fields default such that old clients ignoring them
      still work.
- [ ] This document updated to match.
