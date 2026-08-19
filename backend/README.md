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

Four scanners run per scan. Each covers a different capability, and a
missing tool doesn't fail the scan — it just means that capability silently
produces **zero findings** unless you check `scan.error`, which names the
scanner that couldn't run (e.g. `"depcheck_scan: dependency-check.sh is not
installed"`). A clean report and a broken scanner look identical unless you
read that field.

| Tool | Capability | Install |
|---|---|---|
| **Semgrep** | static analysis / code injection, hardcoded secrets in source | `pip install -r requirements.txt` (already listed) |
| **Lizard** | vibe debt: cyclomatic complexity, duplicated logic | `pip install -r requirements.txt` (already listed) |
| **Gitleaks** | secret scanning (API keys, tokens in git history/files) | `brew install gitleaks`, or a release from https://github.com/gitleaks/gitleaks/releases |
| **OWASP Dependency-Check** | vulnerable dependencies, copyleft license flags | needs Java 11+ (macOS ships a stub `java` that is *not* a real runtime — check `java -version` actually prints a version, not an "install Java" prompt). Download from https://github.com/jeremylong/DependencyCheck/releases and put `dependency-check.sh` on your PATH. |

Dependency-Check also needs its CVE database populated before first use —
`--noupdate` (used here so every scan isn't rebuilding the database) reuses a
local cache that starts out empty:

```bash
dependency-check.sh --updateonly
```

This pulls the full NVD feed and can take a while on a bare cache; it's
**much faster with an NVD API key** (`export NVD_API_KEY=...` first — get one
at https://nvd.nist.gov/developers/request-an-api-key).

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

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
python -m pytest -v
```

Scanner tests that need a missing binary skip themselves rather than fail.
`tests/test_scan_pipeline.py` is the one end-to-end test that runs the real
scanners against a fixture repo with a planted secret, a vulnerable
dependency, and duplicated code — it's slower than the rest of the suite
(semgrep alone takes several seconds and reaches the network for its
ruleset) and is the strongest signal that the whole pipeline actually works,
not just its pieces in isolation.

## Using the status endpoint as a CI gate

```bash
curl -s "http://localhost:8000/scans/$SCAN_ID/status?fail_on=high" | jq -e '.passed'
```
