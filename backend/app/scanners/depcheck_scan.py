import json
import re
import tempfile
from pathlib import Path

from app.scanners.base import RawFinding, ScannerUnavailable, normalize_severity, run_tool

TOOL = "dependency-check"
# \bGPL deliberately does not match LGPL — a word boundary needs a non-word char before it.
_COPYLEFT = [("AGPL", re.compile(r"AGPL", re.I)), ("GPL", re.compile(r"\bGPL", re.I))]


def is_copyleft(license_text: str) -> str | None:
    """Return the copyleft family (AGPL/GPL) this license belongs to, if any."""
    for name, pattern in _COPYLEFT:
        if pattern.search(license_text or ""):
            return name
    return None


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    # Dependency-Check reads manifests, not individual source files, so diff mode
    # scans the whole tree — a changed lockfile affects every dependency.
    with tempfile.TemporaryDirectory() as out_dir:
        cmd = ["dependency-check.sh", "--scan", ".", "--format", "JSON",
               "--out", out_dir, "--project", "vibeguard", "--noupdate"]
        run_tool(cmd, cwd=workspace)
        report_path = Path(out_dir) / "dependency-check-report.json"
        if not report_path.exists():
            return []
        try:
            report = json.loads(report_path.read_text())
        except json.JSONDecodeError:
            return []

    findings = []
    for dependency in report.get("dependencies", []):
        name = dependency.get("fileName", "unknown dependency")
        manifest = Path(dependency.get("filePath", "")).name

        for vuln in dependency.get("vulnerabilities", []):
            findings.append(
                RawFinding(
                    tool=TOOL,
                    severity=normalize_severity(vuln.get("severity", "")),
                    file=manifest,
                    line=0,
                    message=f"{name}: {vuln.get('name', 'vulnerability')} — "
                            f"{vuln.get('description', '')[:300]}",
                    category="security",
                )
            )

        family = is_copyleft(dependency.get("license", ""))
        if family:
            findings.append(
                RawFinding(
                    tool=TOOL,
                    severity="medium",
                    file=manifest,
                    line=0,
                    message=f"{name} is licensed {dependency.get('license')}, a copyleft "
                            f"license that can require you to publish your source.",
                    category="license",
                    license_id=family,
                )
            )
    return findings
