from app.scanners import lizard_scan


def test_flags_duplicate_function_bodies(fixture_repo):
    findings = lizard_scan.scan(fixture_repo)
    duplicates = [f for f in findings if "duplicate" in f.message.lower()]
    assert duplicates, "expected the two identical summarize_* bodies to be flagged"
    assert all(f.category == "vibe-debt" for f in duplicates)


def test_flags_high_complexity_function(fixture_repo):
    findings = lizard_scan.scan(fixture_repo)
    complex_findings = [f for f in findings if "complexity" in f.message.lower()]
    assert any("classify" in f.message for f in complex_findings)
    assert all(f.category == "vibe-debt" for f in complex_findings)


def test_all_findings_are_vibe_debt(fixture_repo):
    findings = lizard_scan.scan(fixture_repo)
    assert findings
    assert {f.category for f in findings} == {"vibe-debt"}
    assert {f.tool for f in findings} == {"lizard"}


def test_clean_code_produces_no_findings(tmp_path):
    (tmp_path / "clean.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
    )
    assert lizard_scan.scan(tmp_path) == []


def test_diff_mode_scans_only_changed_files(tmp_path):
    (tmp_path / "messy.py").write_text(
        "def f(a):\n" + "".join(
            f"    if a == {i}:\n        return {i}\n" for i in range(15)
        ) + "    return None\n"
    )
    (tmp_path / "ignored.py").write_text(
        "def g(a):\n" + "".join(
            f"    if a == {i}:\n        return {i}\n" for i in range(15)
        ) + "    return None\n"
    )
    findings = lizard_scan.scan(tmp_path, files=["messy.py"])
    assert findings
    assert {f.file for f in findings} == {"messy.py"}


def test_does_not_false_positive_on_different_logic(tmp_path):
    """Verify normalization does not over-match genuinely different functions."""
    (tmp_path / "different.py").write_text(
        "def sum_data(items):\n"
        "    total = 0\n"
        "    for item in items:\n"
        "        total += item['value']\n"
        "    return total\n"
        "\n"
        "def format_items(entries):\n"
        "    result = []\n"
        "    for entry in entries:\n"
        "        result.append(str(entry))\n"
        "    return result\n"
    )
    findings = lizard_scan.scan(tmp_path)
    duplicates = [f for f in findings if "duplicate" in f.message.lower()]
    assert not duplicates, "different logic should not be flagged as duplicates"
