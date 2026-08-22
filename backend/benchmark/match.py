from dataclasses import dataclass, field

from app.scanners.base import RawFinding

# Vibe-debt and drift findings are threshold judgements and "look here too"
# signals, not assertions that a defect exists. Scoring them as true or false
# positives would muddy the security number this benchmark exists to produce.
SCORED_CATEGORIES = {"security", "license"}


@dataclass(frozen=True)
class Label:
    file: str
    line: int
    tool: str | None = None
    note: str = ""


@dataclass
class Outcome:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    unmatched: list[RawFinding] = field(default_factory=list)
    missed: list[Label] = field(default_factory=list)

    @property
    def precision(self) -> float:
        reported = self.true_positives + self.false_positives
        return 1.0 if reported == 0 else self.true_positives / reported

    @property
    def recall(self) -> float:
        real = self.true_positives + self.false_negatives
        return 1.0 if real == 0 else self.true_positives / real

    @property
    def false_positive_rate(self) -> float:
        return 1.0 - self.precision


def _matches(f: RawFinding, label: Label, tolerance: int) -> bool:
    if label.tool and f.tool != label.tool:
        return False
    return f.file == label.file and abs(f.line - label.line) <= tolerance


def match(findings: list[RawFinding], labels: list[Label], tolerance: int) -> Outcome:
    """Score one repo's findings against its hand-labeled true positives.

    Each label absorbs at most one finding, so a scanner reporting the same
    issue five times books one hit and four false positives.
    """
    outcome = Outcome()
    remaining = list(labels)
    for f in findings:
        if f.category not in SCORED_CATEGORIES:
            continue
        hit = next((l for l in remaining if _matches(f, l, tolerance)), None)
        if hit is None:
            outcome.false_positives += 1
            outcome.unmatched.append(f)
        else:
            remaining.remove(hit)
            outcome.true_positives += 1
    outcome.false_negatives = len(remaining)
    outcome.missed = remaining
    return outcome
