#!/usr/bin/env bash
# Mirrors ROADMAP.md into GitHub Issues using the GitHub CLI.
#
# Prereqs:
#   - `gh` installed and authenticated: `gh auth login`
#   - run from inside the repo, after `git remote add origin <your-repo-url>`
#
# Usage:
#   ./scripts/create_issues.sh
#
# This is intentionally a flat list of `gh issue create` calls rather
# than something that parses ROADMAP.md automatically - the roadmap is
# prose meant for humans to edit; keeping issue creation as an explicit,
# reviewable script avoids surprising bulk-creates from an ambiguous
# checkbox parse.
set -euo pipefail

create() {
  local title="$1" body="$2" label="$3"
  echo "Creating: $title"
  gh issue create --title "$title" --body "$body" --label "$label"
}

create "Fine-tune MMDetection on labeled conveyor frames" \
  "Replace the class-agnostic COCO-pretrained detector with a fine-tuned single-class 'bag' checkpoint. See README 'Approach to Counting Bags' and ROADMAP.md." \
  "enhancement"

create "Swap SQLite for Postgres" \
  "Change sqlite_url in config.py to a postgresql:// URL and add a db service to docker-compose.yml. Needed for multi-instance deployment." \
  "enhancement"

create "Replace status polling with SSE/WebSocket" \
  "Push job progress instead of polling GET /api/v1/videos/{id}. Keep polling as a fallback." \
  "enhancement"

create "Add GPU image variant" \
  "Publish a second image tag built with a CUDA torch wheel and BC_MMDET_DEVICE=cuda:0." \
  "enhancement"

create "CI: build and publish the full image on release tags" \
  "The lite image (SKIP_ML_STACK=true) is sanity-built on every PR; the full ML image should be built and pushed on release tags." \
  "ci"

create "Add authentication/authorization to the API" \
  "Currently unauthenticated - anyone reaching the API can upload and list all jobs." \
  "security"

create "Job/data retention policy" \
  "uploads/ and processed/ under ./data accumulate forever - add a retention/cleanup policy." \
  "enhancement"

create "Paginate GET /api/v1/videos" \
  "Currently returns every job unpaginated." \
  "enhancement"

create "Tighten mypy: disallow_untyped_defs module by module" \
  "Start with app/services and app/repositories, see [tool.mypy] in backend/pyproject.toml." \
  "tooling"

create "Enforce Conventional Commits via commit-msg hook" \
  "CONTRIBUTING.md currently lists this as preferred-but-not-enforced." \
  "tooling"

create "Add Dependabot config for requirements/*.txt" \
  "Automated version-bump PRs for base/cv/dev requirement files." \
  "tooling"

echo "Done."
