import json
from pathlib import Path

from app.scanners.base import RawFinding, ScannerUnavailable, normalize_severity, run_tool

TOOL = "semgrep"


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    targets = files if files else ["."]
    cmd = ["semgrep", "scan", "--config", "auto", "--json", "--quiet",
           "--no-git-ignore", "--metrics", "off", *targets]
    result = run_tool(cmd, cwd=workspace)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Semgrep failed hard (bad config, network, crash). No findings, not a fatal error.
        return []

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
