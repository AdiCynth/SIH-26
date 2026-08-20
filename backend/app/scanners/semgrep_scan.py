import json
from pathlib import Path

from app.scanners.base import RawFinding, ScannerUnavailable, normalize_severity, run_tool

TOOL = "semgrep"


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    targets = files if files else ["."]
    cmd = ["semgrep", "scan", "--config", "auto", "--json", "--quiet",
           "--no-git-ignore", *targets]
    result = run_tool(cmd, cwd=workspace)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Semgrep failed hard (bad config, network, crash). A tool that could not run
        # must raise: returning [] here would report a broken scanner as a clean scan.
        raise ScannerUnavailable(
            f"semgrep exited {result.returncode} without JSON: {result.stderr.strip()[:200]}"
        )
    # Valid JSON can still carry a failure: a partial rule download leaves results
    # empty and errors populated, which is indistinguishable from "clean" downstream.
    if not payload.get("results") and payload.get("errors"):
        raise ScannerUnavailable(
            f"semgrep errored: {payload['errors'][0].get('message', '')[:200]}"
        )

    findings = []
    for item in payload.get("results", []):
        extra = item.get("extra", {})
        findings.append(
            RawFinding(
                tool=TOOL,
                severity=normalize_severity(extra.get("severity", "")),
                file=item.get("path", ""),
                line=item.get("start", {}).get("line", 0),
                message=extra.get("message", item.get("check_id", "Semgrep finding")),
                category="security",
            )
        )
    return findings
