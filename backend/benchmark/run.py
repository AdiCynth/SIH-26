"""Measure the scanners' false-positive rate against a hand-labeled corpus.

    python -m benchmark.run           # score the corpus, exit 1 if off target
    python -m benchmark.run --dump    # print raw findings, for labeling
"""

import argparse
import json
import sys
from pathlib import Path

from app.scanners import deps_scan, gitleaks_scan, semgrep_scan
from app.scanners.base import ScannerUnavailable
from benchmark.match import SCORED_CATEGORIES, Label, match

# Only the scanners that make security claims. Lizard and drift emit categories
# this benchmark does not score, so running them would just cost time.
SCANNERS = [semgrep_scan, gitleaks_scan, deps_scan]

ROOT = Path(__file__).resolve().parent.parent
LABELS = Path(__file__).parent / "labels.json"


def _scan(repo: Path):
    findings = []
    for scanner in SCANNERS:
        # A scanner that cannot run must abort the benchmark. Skipping it would
        # silently drop both its true and false positives and report a
        # precision figure for a tool set that never ran.
        try:
            findings.extend(scanner.scan(repo, None))
        except ScannerUnavailable as exc:
            sys.exit(f"ABORT: {scanner.__name__} unavailable ({exc}). "
                     f"Install it — a partial run reports a meaningless rate.")
    return findings


def _dump(config) -> None:
    for entry in config["corpus"]:
        repo = ROOT / entry["repo"]
        print(f"\n=== {entry['repo']} ===")
        for f in sorted(_scan(repo), key=lambda f: (f.file, f.line)):
            if f.category in SCORED_CATEGORIES:
                print(f'  {{"file": "{f.file}", "line": {f.line}, '
                      f'"tool": "{f.tool}", "note": "{f.message[:60]}"}},')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write full results here")
    parser.add_argument("--dump", action="store_true",
                        help="print raw findings as label stubs, then exit")
    args = parser.parse_args()

    config = json.loads(LABELS.read_text())
    if args.dump:
        _dump(config)
        return 0

    tolerance = config["line_tolerance"]
    target = config["target_false_positive_rate"]
    totals = {"tp": 0, "fp": 0, "fn": 0}
    rows, detail = [], []

    for entry in config["corpus"]:
        repo = ROOT / entry["repo"]
        if not repo.is_dir():
            sys.exit(f"ABORT: corpus entry {entry['repo']} does not exist")
        labels = [Label(**item) for item in entry["expected"]]
        outcome = match(_scan(repo), labels, tolerance)
        totals["tp"] += outcome.true_positives
        totals["fp"] += outcome.false_positives
        totals["fn"] += outcome.false_negatives
        rows.append((entry["repo"], outcome))
        detail.append({
            "repo": entry["repo"],
            "true_positives": outcome.true_positives,
            "false_positives": outcome.false_positives,
            "false_negatives": outcome.false_negatives,
            "precision": round(outcome.precision, 4),
            "recall": round(outcome.recall, 4),
            "spurious": [f"{f.tool} {f.file}:{f.line} {f.message[:70]}"
                         for f in outcome.unmatched],
            "missed": [f"{l.file}:{l.line} {l.note}" for l in outcome.missed],
        })

    reported = totals["tp"] + totals["fp"]
    fp_rate = 0.0 if reported == 0 else totals["fp"] / reported
    real = totals["tp"] + totals["fn"]
    recall = 1.0 if real == 0 else totals["tp"] / real

    print(f"\n{'repo':<40} {'TP':>4} {'FP':>4} {'FN':>4} {'prec':>7}")
    print("-" * 62)
    for name, outcome in rows:
        print(f"{name:<40} {outcome.true_positives:>4} "
              f"{outcome.false_positives:>4} {outcome.false_negatives:>4} "
              f"{outcome.precision:>7.1%}")
    print("-" * 62)
    print(f"{'TOTAL':<40} {totals['tp']:>4} {totals['fp']:>4} "
          f"{totals['fn']:>4} {1 - fp_rate:>7.1%}")
    # This is the share of reported findings that were wrong (FP / (TP + FP)),
    # i.e. false discovery rate in the textbook sense — not FP / (FP + TN).
    # That's the definition scanner vendors mean by "false-positive rate" and
    # the one this benchmark measures; spelled out here since the number is
    # meant to be quoted on its own.
    print(f"\nfalse-positive rate: {fp_rate:.1%}  "
          f"(share of reported findings that were wrong: "
          f"FP/(TP+FP) = {totals['fp']}/{reported}; "
          f"target <= {target:.0%})")
    print(f"recall:              {recall:.1%}")

    for item in detail:
        for line in item["spurious"]:
            print(f"  FP  {item['repo']}: {line}")
        for line in item["missed"]:
            print(f"  FN  {item['repo']}: {line}")

    if args.json:
        args.json.write_text(json.dumps({
            "false_positive_rate": round(fp_rate, 4),
            "precision": round(1 - fp_rate, 4),
            "recall": round(recall, 4),
            "target_false_positive_rate": target,
            "totals": totals,
            "per_repo": detail,
        }, indent=2))

    if fp_rate > target:
        print(f"\nFAIL: {fp_rate:.1%} false positives exceeds the "
              f"{target:.0%} target")
        return 1
    print(f"\nPASS: within the {target:.0%} false-positive target")
    return 0


if __name__ == "__main__":
    sys.exit(main())
