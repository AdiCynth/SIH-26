import json
import re
from pathlib import Path

from app.scanners.base import RawFinding, ScannerUnavailable, run_tool

TOOL = "osv-scanner"
# \bGPL deliberately does not match LGPL — a word boundary needs a non-word char before it.
_COPYLEFT = [("AGPL", re.compile(r"AGPL", re.I)), ("GPL", re.compile(r"\bGPL", re.I))]


def is_copyleft(license_text: str) -> str | None:
    """Return the copyleft family (AGPL/GPL) this license belongs to, if any."""
    for name, pattern in _COPYLEFT:
        if pattern.search(license_text or ""):
            return name
    return None


def _severity_from_score(score: str | None) -> str:
    """Map a CVSS numeric string (osv-scanner's max_severity) onto our vocabulary."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "medium"
    if value >= 9.0:
        return "critical"
    if value >= 7.0:
        return "high"
    if value >= 4.0:
        return "medium"
    if value > 0:
        return "low"
    return "medium"


def scan(workspace: Path, files: list[str] | None = None) -> list[RawFinding]:
    # osv-scanner reads manifests, not individual source files, so diff mode is
    # ignored — a changed lockfile affects every dependency in it.
    cmd = ["osv-scanner", "scan", "source", "--format", "json", "--recursive",
           "--allow-no-lockfiles", "--licenses=MIT", "."]
    result = run_tool(cmd, cwd=workspace)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        # osv-scanner exits 1 when it simply finds vulnerabilities — that's a normal,
        # successful run and still prints valid JSON. Anything that leaves stdout
        # unparseable (bad flags, a path it couldn't resolve, a crash) is a real
        # failure and must raise, never return [] — [] would report a broken
        # scanner as a clean one.
        raise ScannerUnavailable(
            f"osv-scanner exited {result.returncode} without JSON: {result.stderr.strip()[:200]}"
        )

    findings = []
    for entry in payload.get("results") or []:
        manifest = Path(entry.get("source", {}).get("path", "")).name
        for pkg in entry.get("packages", []):
            package = pkg.get("package", {})
            name = package.get("name", "unknown package")
            version = package.get("version", "")

            for group in pkg.get("groups", []):
                ids = group.get("aliases") or group.get("ids") or []
                findings.append(
                    RawFinding(
                        tool=TOOL,
                        severity=_severity_from_score(group.get("max_severity")),
                        file=manifest,
                        line=0,
                        message=f"{name} {version}: {', '.join(ids) or 'known vulnerability'}",
                        category="security",
                    )
                )

            for license_id in pkg.get("licenses") or []:
                family = is_copyleft(license_id)
                if family:
                    findings.append(
                        RawFinding(
                            tool=TOOL,
                            severity="medium",
                            file=manifest,
                            line=0,
                            message=f"{name} {version} is licensed {license_id}, a copyleft "
                                    f"license that can require you to publish your source.",
                            category="license",
                            license_id=family,
                        )
                    )
    return findings
