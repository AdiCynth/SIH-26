import json
import tempfile
from pathlib import Path

from app.scanners.base import RawFinding, ScannerUnavailable, run_tool

TOOL = "gitleaks"


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    with tempfile.TemporaryDirectory() as report_dir:
        report_path = Path(report_dir) / "gitleaks.json"
        cmd = ["gitleaks", "detect", "--no-git", "--source", ".",
               "--report-format", "json", "--report-path", str(report_path),
               "--exit-code", "0", "--redact"]
        # Let ScannerUnavailable propagate; the pipeline layer handles it.
        result = run_tool(cmd, cwd=workspace)

        # No parseable report after the tool actually ran means it failed, not that
        # the repo is clean. Only a valid report with zero entries is a clean run.
        if not report_path.exists():
            raise ScannerUnavailable(
                f"gitleaks exited {result.returncode} without a report: "
                f"{result.stderr.strip()[:200]}"
            )
        try:
            report = json.loads(report_path.read_text() or "[]")
        except json.JSONDecodeError:
            raise ScannerUnavailable(
                f"gitleaks exited {result.returncode} with an unreadable report: "
                f"{result.stderr.strip()[:200]}"
            )

    changed = set(files) if files else None
    findings = []
    for leak in report or []:
        path = leak.get("File", "")
        if changed is not None and path not in changed:
            continue
        findings.append(
            RawFinding(
                tool=TOOL,
                severity="high",  # A committed credential is never "low".
                file=path,
                line=leak.get("StartLine", 0),
                message=f"{leak.get('Description', 'Secret detected')} "
                        f"(rule: {leak.get('RuleID', 'unknown')})",
                category="security",
            )
        )
    return findings
