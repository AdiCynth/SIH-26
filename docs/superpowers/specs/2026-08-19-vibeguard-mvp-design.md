# VibeGuard MVP — Design Spec

Date: 2026-08-19
Status: Approved for implementation planning

## Background

VibeGuard is an AI-powered security & code-quality analyzer for "vibe-coded"
applications (SIH26_139, team "Trust Me Bro"). The pitch deck describes a
full product with sandboxed execution, fuzzing/mutation testing, a "Tribal
Knowledge Graph", and an "Integration Drift Simulator". That's several
independent subsystems — too large for one spec or one implementation pass.

This spec covers **sub-project 1: the core scan pipeline** — everything
needed for a working SIH demo. Later sub-projects (sandboxing, fuzzing,
Tribal Knowledge Graph, Integration Drift Simulator, IDE plugin) are
deliberately out of scope here and get their own specs later, only if time
permits.

## Goal

A working MVP: a user logs in, submits a repo (GitHub URL or zip), the
scanner runs static analysis + dependency checks, an AI reasoning layer
explains and prioritizes the findings, and the user gets back a scored,
actionable report. Re-submitting the same repo shows a score trend.

## Scope

**In scope:**
- Auth (email/password + GitHub OAuth)
- Repo intake via GitHub URL (clone) or zip upload
- Static analysis (Semgrep, language-agnostic default rule sets) + secret
  scanning (Gitleaks) + dependency scanning (OWASP Dependency-Check)
- AI reasoning layer (OpenAI API) — explains impact, prioritizes severity,
  drafts fix suggestions. Never invents findings; only reasons over what the
  deterministic tools already reported.
- Async scan execution with status polling
- Report: severity-sorted findings, security score (0–100), Vibe Debt score
  (0–100), license compliance flags
- Score trend across repeated scans of the same repo
- CI-style status endpoint (`GET /scans/{id}/status?fail_on=high`)
- PR/diff-only scan mode (scan only changed files between two refs)

**Explicitly out of scope for this spec:**
- Docker/QEMU sandboxed dynamic execution
- Fuzzing / mutation testing
- Tribal Knowledge Graph (learning team-specific rules from past PR reviews)
- Integration Drift Simulator (cross-file dependency-graph impact analysis)
- Local IDE plugin / local-only review surface
- Background job queue infra (Celery/Redis) — plain async is enough at this
  scale
- Object storage service — cloned/extracted repos live in a temp dir and are
  deleted after the scan; nothing is served back to the user

## Architecture

```
Next.js (TS, Tailwind)  ──▶  FastAPI backend  ──▶  Postgres
     │                            │                (users, scans, findings)
  Login (email/pw,          Auth endpoints
  GitHub OAuth)              │
  Submit scan form           Intake handler
  (repo URL / zip /          (git clone or zip extract → temp workspace)
  PR diff refs)              │
  Poll scan status           Scan runner (subprocess):
  Report view                  - Semgrep (default rule sets, all languages)
  (findings, scores,           - Gitleaks
  trend, license flags)        - OWASP Dependency-Check
                              │
                            Parse tool output → findings table
                              │
                            AI reasoning call (OpenAI API):
                              explain impact, assign priority,
                              draft fix suggestion per finding
                              │
                            Scoring: security score + Vibe Debt score
                              │
                            Persist scan + findings, mark scan "done"
```

## Components

### Frontend (Next.js + TypeScript + Tailwind)
- Auth pages: email/password signup+login, "Sign in with GitHub".
- Scan submission form: GitHub repo URL, or zip upload, or (for diff mode)
  base/head refs.
- Scan status view: polls `GET /scans/{id}` until `done`/`failed`.
- Report view: findings sorted by severity, each with explanation + fix
  suggestion; security score and Vibe Debt score; license compliance
  warnings; a trend line of past scores for the same repo (from
  `GET /scans?repo_key=`).

### Backend (FastAPI)
- Auth: session/JWT-based email+password, GitHub OAuth flow.
- `POST /scans`: accepts repo URL, zip, or diff refs; creates a `scans` row
  with status `pending`; kicks off a `BackgroundTasks` job; returns the scan
  id immediately.
- `GET /scans/{id}`: returns current status and, once done, the full report.
- `GET /scans/{id}/status?fail_on=<severity>`: pass/fail + score, for CI use.
- `GET /scans?repo_key=`: past scans for the same repo, for the trend view.
- Intake handler: clones the repo (or extracts the zip, or checks out a
  diff range) into a temp workspace; deletes it after the scan regardless of
  outcome.
- Scan runner: shells out to Semgrep, Gitleaks, and OWASP Dependency-Check
  against the workspace (or, in diff mode, just the changed files); parses
  each tool's JSON output into a common `findings` shape.
- AI reasoning step: sends the raw findings to the OpenAI API, asking it to
  explain impact, assign a priority, and suggest a fix per finding. If this
  call fails, the report still ships with raw findings; the
  explanation/fix fields are marked "unavailable" rather than blocking the
  report.
- Scoring: security score from finding severity/count; Vibe Debt score from
  Semgrep's complexity/duplicate-code findings. Both 0–100.
- License flags: read the license field already returned by OWASP
  Dependency-Check per dependency; flag GPL/AGPL.

### Data layer (Postgres)
- `users`: id, email, password_hash (nullable if GitHub-only), github_id
  (nullable), created_at.
- `scans`: id, user_id, repo_key (normalized repo identity, e.g. GitHub
  `owner/repo` or a hash of the zip), mode (`full` | `diff`), status
  (`pending`/`running`/`done`/`failed`), security_score, vibe_debt_score,
  created_at.
- `findings`: id, scan_id, tool (`semgrep`/`gitleaks`/`dependency-check`),
  severity, file, line, message, ai_explanation (nullable), ai_fix
  (nullable), category (`security`/`vibe-debt`/`license`), license_id
  (nullable).

## Error handling
- Bad repo URL, unreachable repo, or malformed zip → `400` with a clear
  message; scan is never created.
- A scan tool crashing → scan continues with the other tools; scan is
  marked `failed` only if *all* tools fail to produce output, otherwise it
  completes with partial findings and a note on which tool didn't run.
- OpenAI call failure/timeout → report ships with raw findings; explanation
  and fix fields marked "unavailable". Does not fail the scan.
- Intake workspace is always cleaned up (success or failure) via a
  try/finally around the scan runner.

## Testing
- One `test_scan_pipeline.py`: runs the full pipeline against a small
  fixture repo containing a planted secret (Gitleaks should catch it), a
  known-vulnerable dependency (Dependency-Check should catch it), and an
  obviously duplicated code block (Vibe Debt score should reflect it).
  Asserts all three show up in the resulting report. This is the one check
  that fails if the scan pipeline breaks.

## Open questions / risks
- Semgrep's default/auto rule sets vary in noise level across languages;
  false-positive triage relies on the AI reasoning step, per the deck's own
  "Key Challenges" slide — no extra dedup logic planned for MVP.
- Large repos scanned synchronously by the tools (even though the API call
  is async) could be slow; no timeout/size cap is specified yet — add one
  if a demo repo turns out to hang.

## Implementation deviations

Recorded here rather than edited into the sections above, so the spec still
reflects what was originally approved.

**Vibe Debt scoring: lizard instead of Semgrep complexity/duplicate rules.**
This spec derives the Vibe Debt score from "Semgrep complexity/duplicate-code
rule findings" (see Components → Backend, above). Semgrep's public registry
has almost no cross-language complexity or duplicate-detection rules, so
that path would have produced an empty score. The implementation uses
**lizard** instead (pip package, Python API, ~15 languages) for cyclomatic
complexity and long functions, plus a normalized-body hash for duplicate
detection — same output, same score, a tool that actually does the job.

**2026-08-20 — OWASP Dependency-Check replaced with osv-scanner.**
Dependency-Check (referenced throughout this spec as the dependency/license
scanner) requires a JDK plus a multi-gigabyte NVD database download and had
never actually run in this environment — its integration test was the
suite's one permanent skip. It was replaced with **osv-scanner** (Google), a
single Go binary with no database step: `osv-scanner scan source --format
json` reports the same vulnerabilities (verified against the fixture repo's
known-vulnerable Flask pin) and, with `--licenses=<allowlist>`, still returns
a per-package SPDX license id, so the GPL/AGPL license-flagging feature
described above is unaffected. Net effect: lighter dependency footprint, no
Java requirement anywhere in the project, license data retained.
