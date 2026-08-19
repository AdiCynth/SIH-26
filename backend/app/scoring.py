from app.scanners.base import RawFinding

SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]

_PENALTY = {"critical": 25, "high": 15, "medium": 7, "low": 3, "info": 1}
_SECURITY_CATEGORIES = {"security", "license"}
# ponytail: flat 4 points per finding. Normalize by lines-of-code if big repos
# start bottoming out the score unfairly.
_VIBE_DEBT_PENALTY = 4


def security_score(findings: list[RawFinding]) -> int:
    penalty = sum(
        _PENALTY.get(f.severity, 1)
        for f in findings
        if f.category in _SECURITY_CATEGORIES
    )
    return max(0, 100 - penalty)


def vibe_debt_score(findings: list[RawFinding]) -> int:
    count = sum(1 for f in findings if f.category == "vibe-debt")
    return max(0, 100 - _VIBE_DEBT_PENALTY * count)


def meets_threshold(findings: list[RawFinding], fail_on: str) -> bool:
    """False when any finding is at or above the fail_on severity."""
    cutoff = SEVERITY_ORDER.index(fail_on)
    return not any(
        SEVERITY_ORDER.index(f.severity) >= cutoff
        for f in findings
        if f.severity in SEVERITY_ORDER
    )
