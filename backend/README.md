# VibeGuard Backend

## Setup

Requires **Python 3.11** specifically (not 3.12+, not 3.14). Semgrep cannot
even be imported on Python 3.14 — pin the venv to 3.11 or scans will fail
before they start.

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in OPENAI_API_KEY and the GitHub OAuth pair
```

Postgres:

```bash
createdb vibeguard
```

## Scanner setup

Four scanners run per scan. Each covers a different capability. A tool that
**ran and found nothing** contributes zero findings; a tool that **could not
run** — missing binary, crash, unreadable output, semgrep unable to reach
its ruleset — raises, and is named in `scan.error` (e.g. `"deps_scan:
osv-scanner is not installed"`). A partial failure still produces a
report with `status="done"`; only an all-scanner failure marks the scan
`failed`. A clean repo and a broken scanner are never reported the same way.

| Tool | Capability | Install |
|---|---|---|
| **Semgrep** | static analysis / code injection, hardcoded secrets in source | `pip install -r requirements.txt` (already listed) |
| **Lizard** | vibe debt: cyclomatic complexity, duplicated logic | `pip install -r requirements.txt` (already listed) |
| **Gitleaks** | secret scanning (API keys, tokens in git history/files) | `brew install gitleaks`, or a release from https://github.com/gitleaks/gitleaks/releases |
| **osv-scanner** | vulnerable dependencies, copyleft license flags | `brew install osv-scanner`, or a release from https://github.com/google/osv-scanner/releases. No database step — it's a single binary that queries the OSV API (or bundled offline data) on each run. |

### Semgrep telemetry

Semgrep's `--config auto` (used here to pull the default community ruleset)
requires Semgrep metrics to be enabled — it hard-errors if you set
`--metrics off`. That means every scan sends pseudonymous usage data to
semgrep.dev. This is a deployment decision, not a bug: if that's not
acceptable for your environment, you'd need to switch to a pinned local
ruleset instead of `auto`.

### OPENAI_API_KEY is optional

Without it, scans still complete and reports still ship — findings just
carry only the raw scanner output, with no AI-generated explanation or fix.
`scan.ai_available` is `false` in that case so the frontend can show that the
explanations are missing rather than pretending they don't exist.

## Deploying off localhost

Two settings only matter once the app leaves your laptop, and both fail in
ways that look like something else:

**`JWT_SECRET`** — the built-in default is a known literal, so any instance
running on it has forgeable sessions for an arbitrary `user_id`. The app
refuses to start if `JWT_SECRET` is still the default and `FRONTEND_URL` is
not localhost. Generate one with:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

**`COOKIE_CROSS_SITE`** — leave it `false` when frontend and backend share a
host (localhost counts: ports don't affect SameSite). Set it `true` when they
are on different hosts, which switches the session cookie from
`SameSite=Lax` to `SameSite=None; Secure`. Get this wrong and the browser
silently drops the cookie on every `credentials: "include"` fetch: login
appears to succeed and every request after it 401s, which reads as an auth
bug rather than a cookie-policy one. `SameSite=None` requires `Secure`, so
cross-site deployments must be served over https.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
python -m pytest -v
```

Most per-scanner tests that need a missing binary skip themselves rather
than fail. `tests/test_scan_pipeline.py` is different: it never skips — it
always runs the real pipeline and narrows which assertions it makes
depending on which binaries are present, so it stays the one test that
fails outright if the pipeline itself breaks, even with tools missing. It
runs against a fixture repo with a planted secret, a vulnerable dependency,
and duplicated code, and it's slower than the rest of the suite (semgrep
alone takes several seconds and reaches the network for its ruleset) — it's
the strongest signal that the whole pipeline actually works, not just its
pieces in isolation.

## Using the status endpoint as a CI gate

```bash
curl -s "http://localhost:8000/scans/$SCAN_ID/status?fail_on=high" | jq -e '.passed'
```

## Measuring the false-positive rate

The AI reasoning layer cannot invent findings — it annotates the exact index
list it is given, and out-of-range indexes are dropped
(`tests/test_reasoning.py::test_extra_annotations_are_discarded`). That is a
property of the architecture, not a rate.

The *scanners* do produce false positives, and that rate is measured:

```bash
python -m benchmark.run --json benchmark/results.json
```

The runner scans each repo in `benchmark/labels.json`, matches findings against
hand-labeled true positives (same file, line within 2, tool if the label names
one), and reports precision, recall, and the false-positive rate. "False-positive
rate" here means the false *discovery* rate — the share of reported findings
that turned out wrong, `FP / (TP + FP)` — not `FP / (FP + TN)`; the printed
line spells this out since the number is meant to be quoted on its own. One
label absorbs one finding, so a scanner that repeats itself books the repeats
as false positives. Only `security` and `license` findings are scored —
vibe-debt and drift are threshold and impact signals, not defect claims.

It exits non-zero above the target rate in `labels.json`, so it works in CI.
A scanner that is not installed aborts the run rather than being skipped: a
partial run would silently drop that tool's false positives and report a
flattering number for a tool set that never ran.
