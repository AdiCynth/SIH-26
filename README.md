# VibeGuard

VibeGuard is an AI-assisted security and code-quality scanner for
"vibe-coded" applications — repos written fast, often with AI help, where
nobody's had time to audit them. Submit a GitHub repo URL or a zip; get back
a scored report of security issues, leaked secrets, vulnerable dependencies,
and code-quality debt, each with an AI-generated explanation and suggested
fix where possible.

## What it catches

Four scanners run per scan, each covering a different capability:

| Tool | Catches |
|---|---|
| **Semgrep** | Static analysis findings — injection, unsafe patterns, hardcoded secrets in source, across languages via its default `auto` ruleset |
| **Gitleaks** | Committed secrets — API keys, tokens, credentials in files (and git history, if present) |
| **osv-scanner** | Known-vulnerable dependencies (CVE/OSV advisories) and copyleft license flags (AGPL/GPL) read off each dependency's manifest |
| **Lizard** | "Vibe debt" — cyclomatic complexity and duplicated code, the kind of mess that accumulates when code ships faster than it's reviewed |

A tool that ran and found nothing contributes zero findings. A tool that
*could not run* (missing binary, crash, unparseable output) raises instead
of silently reporting a clean scan, and is named in `scan.error` on the
report. A scan only fails outright if every scanner fails; a partial
failure still produces a report.

An AI reasoning layer (OpenAI API) then annotates each raw finding with an
explanation and a suggested fix. It never invents findings — it only
reasons over what the deterministic scanners already reported — and if the
call fails or no API key is configured, the report still ships with the raw
findings intact.

## Architecture

```
Next.js frontend  ──▶  FastAPI backend  ──▶  Postgres
(auth, submit scan,     (auth, intake,        (users, scans, findings)
 poll status, report)    scan pipeline,
                          AI reasoning,
                          scoring)
```

A scan submission clones the repo (or extracts the zip, or checks out a
diff range) into a temp workspace, runs the four scanners against it,
sends the combined findings to the AI reasoning layer, scores the result,
and persists everything. The frontend polls the scan until it's `done` or
`failed`.

## Quickstart

**Backend** (Python 3.11 — see `backend/README.md` for why the pin matters):

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY (optional) and GitHub OAuth
createdb vibeguard
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

See `backend/README.md` for scanner installs (Semgrep and Lizard come from
`requirements.txt`; Gitleaks and osv-scanner are separate binaries) and
deployment notes (`JWT_SECRET`, `COOKIE_CROSS_SITE`).

## Docs

- Design spec: `docs/superpowers/specs/2026-08-19-vibeguard-mvp-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-19-vibeguard-mvp.md`

## Current limitations

Being upfront about what this MVP doesn't handle yet:

- **The security score floors at 0.** A repo with a handful of high-severity
  findings and a repo riddled with critical ones can both read `0` — the
  score can't distinguish "bad" from "catastrophic" once it bottoms out.
- **A killed backend process strands a scan at `running`.** There's no
  reaper: if the process running a scan dies mid-scan, that scan's status
  never advances and nothing reclaims it.
- **Semgrep's `--config auto` requires telemetry.** It hard-errors on
  `--metrics off`, so every scan sends pseudonymous usage data to
  semgrep.dev. Fine for a demo; a deployment that can't accept that needs to
  switch to a pinned local ruleset instead of `auto`.
- **No `OPENAI_API_KEY` means no AI annotations.** Reports still ship, but
  findings carry only the raw scanner output — no generated explanation or
  fix suggestion. `scan.ai_available` reflects this so the frontend can show
  it rather than pretend the fields were never there.
