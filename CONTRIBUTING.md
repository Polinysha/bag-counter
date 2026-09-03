# Contributing / Branching Model

## Branches

* **`main`** - always deployable. Only receives merges from `dev` via a
  reviewed, CI-green PR, after the batch of changes on `dev` has been
  tested (locally / on staging). No direct commits.
* **`dev`** - integration branch. Feature branches merge here first.
  Always expected to build and pass CI, but is allowed to be "ahead of
  production" - this is where things get tested together before a
  `dev -> main` release PR.
* **`feature/<short-name>`** - one focused, independent change, branched
  off `dev`. Keep these small on purpose: a feature branch should touch
  one layer/concern (e.g. `feature/requirements-split`,
  `feature/job-repository`, `feature/lite-docker-build`) so it can be
  reviewed, tested, and merged without waiting on unrelated work, and so
  two feature branches don't conflict just because they both happened to
  touch the same file for unrelated reasons.
* **`fix/<short-name>`** - same idea, for bug fixes.

## Flow for a change

1. Branch from `dev`: `git checkout dev && git pull && git checkout -b feature/my-change`.
2. Commit in small, reviewable chunks. Conventional-commit-style prefixes
   (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`) are preferred
   but not enforced by tooling yet (see ROADMAP.md).
3. Before opening a PR, run `make ci` locally (lint + typecheck + tests) -
   it's the exact same three steps CI runs.
4. Open a PR **into `dev`** (not `main`), fill in `.github/PULL_REQUEST_TEMPLATE.md`,
   link the issue it closes.
5. Once merged into `dev` and the batch has been exercised there, open a
   `dev -> main` PR to release it. `main` should only ever move forward
   through that PR.

## Issues

Planned work lives in [`ROADMAP.md`](ROADMAP.md) and should be mirrored
1:1 into GitHub Issues (`scripts/create_issues.sh` does this via `gh`).
Work an issue by branching as above, referencing `Closes #<n>` in the PR,
and closing items in `ROADMAP.md` as their issue closes so the two don't
drift apart.

## Commit / PR hygiene

* Keep feature branches independent: rebase on `dev` rather than merging
  `dev` back into a long-lived feature branch, and prefer several small
  PRs over one broad one when a task naturally splits by layer (API vs
  worker vs DB vs infra) - that's also why the codebase itself is
  layered that way (see `README.md` "Repository Structure").
* CI (`.github/workflows/ci.yml`) is a required check on PRs into both
  `dev` and `main`.
