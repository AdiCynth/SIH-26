from app.scanners.base import RawFinding
from benchmark.match import Label, match


def finding(file="app.py", line=10, tool="semgrep", category="security"):
    return RawFinding(tool=tool, severity="high", category=category,
                      file=file, line=line, message="issue")


def test_exact_match_is_a_true_positive():
    outcome = match([finding()], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.true_positives == 1
    assert outcome.false_positives == 0
    assert outcome.false_negatives == 0


def test_line_within_tolerance_still_matches():
    outcome = match([finding(line=12)], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.true_positives == 1


def test_line_outside_tolerance_is_a_false_positive_and_a_miss():
    outcome = match([finding(line=40)], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.false_positives == 1
    assert outcome.false_negatives == 1


def test_wrong_file_does_not_match():
    outcome = match([finding(file="other.py")], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.true_positives == 0
    assert outcome.false_positives == 1


def test_label_tool_is_honoured_when_set():
    labels = [Label(file="app.py", line=10, tool="gitleaks")]
    assert match([finding(tool="semgrep")], labels, tolerance=2).true_positives == 0
    assert match([finding(tool="gitleaks")], labels, tolerance=2).true_positives == 1


def test_one_label_absorbs_only_one_finding():
    """Two findings on the same line are one hit and one false positive, so a
    noisy scanner cannot inflate its own precision by repeating itself."""
    outcome = match([finding(), finding()], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.true_positives == 1
    assert outcome.false_positives == 1


def test_vibe_debt_and_drift_findings_are_not_scored():
    findings = [finding(category="vibe-debt"), finding(category="drift")]
    outcome = match(findings, [], tolerance=2)
    assert outcome.false_positives == 0
    assert outcome.unmatched == []


def test_clean_repo_findings_are_all_false_positives():
    outcome = match([finding(), finding(file="b.py")], [], tolerance=2)
    assert outcome.false_positives == 2
    assert outcome.precision == 0.0
    assert outcome.false_positive_rate == 1.0


def test_rates_of_an_empty_run_are_defined():
    outcome = match([], [], tolerance=2)
    assert outcome.precision == 1.0
    assert outcome.recall == 1.0
    assert outcome.false_positive_rate == 0.0


def test_repeat_of_a_labeled_issue_is_a_duplicate_not_spurious():
    """Two findings on one labeled line: the first is a TP, the second is an
    FP — and since it still matches that same real label, it's a duplicate,
    not a spurious (non-issue) finding."""
    outcome = match([finding(), finding()], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.false_positives == 1
    assert outcome.duplicates == 1
    assert outcome.spurious == 0


def test_finding_matching_no_label_is_spurious():
    outcome = match([finding(file="other.py")], [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.false_positives == 1
    assert outcome.spurious == 1
    assert outcome.duplicates == 0


def test_duplicates_plus_spurious_equals_false_positives():
    findings = [finding(), finding(), finding(file="other.py")]
    outcome = match(findings, [Label(file="app.py", line=10)], tolerance=2)
    assert outcome.duplicates + outcome.spurious == outcome.false_positives
