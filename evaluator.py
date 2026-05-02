"""
evaluator.py — AutoBug AI v2 Report Evaluator

Scoring rubric (4 checks, each worth 0.25):
  1. All required fields present (including confidence)
  2. Severity is a valid value (Low / Medium / High / Critical)
  3. Summary >= 30 characters
  4. Root cause and suggested_fix both >= 20 characters

Final score = passed_checks / 4  (rounded to 2 decimal places)
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("summary", "root_cause", "severity", "suggested_fix", "confidence")
VALID_SEVERITIES = {"Low", "Medium", "High", "Critical"}


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def evaluate_report(report: dict) -> Tuple[float, dict]:
    """
    Evaluate the bug report and return (score, checks_detail).

    Args:
        report: Final structured report dict from the pipeline.

    Returns:
        score   -- float in [0.0, 1.0]
        checks  -- dict with per-check results
    """
    checks: dict = {}
    total = 4
    passed = 0

    # Check 1: All required fields present and non-empty
    missing = [
        f for f in REQUIRED_FIELDS
        if f not in report or (isinstance(report[f], str) and not report[f].strip())
    ]
    if not missing:
        checks["all_fields_present"] = {"passed": True, "note": "All required fields found."}
        passed += 1
    else:
        checks["all_fields_present"] = {
            "passed": False, "note": f"Missing or empty fields: {missing}"}

    # Check 2: Severity is valid
    severity = report.get("severity", "")
    if severity in VALID_SEVERITIES:
        checks["severity_valid"] = {
            "passed": True, "note": f"Severity '{severity}' is a valid classification."}
        passed += 1
    else:
        checks["severity_valid"] = {
            "passed": False, "note": f"'{severity}' is not one of {sorted(VALID_SEVERITIES)}."}

    # Check 3: Summary length
    summary_len = len(report.get("summary", ""))
    if summary_len >= 30:
        checks["summary_detailed"] = {
            "passed": True, "note": f"Summary has {summary_len} chars (minimum 30)."}
        passed += 1
    else:
        checks["summary_detailed"] = {
            "passed": False, "note": f"Summary too short: {summary_len} chars (minimum 30)."}

    # Check 4: Root cause + suggested fix non-trivial
    root_len = len(report.get("root_cause", ""))
    fix_len  = len(report.get("suggested_fix", ""))
    if root_len >= 20 and fix_len >= 20:
        checks["root_and_fix_detailed"] = {
            "passed": True,
            "note": f"root_cause={root_len} chars, suggested_fix={fix_len} chars (both >= 20)."}
        passed += 1
    else:
        checks["root_and_fix_detailed"] = {
            "passed": False,
            "note": f"root_cause={root_len} chars, suggested_fix={fix_len} chars (both need >= 20)."}

    score = round(passed / total, 2)
    logger.info("[Evaluator] Score: %.2f (%d/%d checks passed).", score, passed, total)
    return score, checks


def print_evaluation(score: float, checks: dict, overall_confidence: float) -> None:
    """Pretty-print evaluation results."""
    bar_filled = int(score * 20)
    bar = "#" * bar_filled + "." * (20 - bar_filled)

    print("\n" + "=" * 60)
    print("  [EVALUATION REPORT]")
    print("=" * 60)
    print(f"  Score      : {score:.2f} / 1.00   [{bar}]")
    print(f"  Grade      : {_grade(score)}")
    print(f"  Confidence : {overall_confidence:.2f}  (avg across all agents)")
    print("-" * 60)
    for name, result in checks.items():
        icon  = "[PASS]" if result["passed"] else "[FAIL]"
        label = name.replace("_", " ").title()
        print(f"  {icon}  {label}")
        print(f"       -> {result['note']}")
    print("=" * 60 + "\n")


def _grade(score: float) -> str:
    if score == 1.0:
        return "PASS -- Excellent"
    if score >= 0.75:
        return "PASS -- Good"
    if score >= 0.50:
        return "PARTIAL -- Needs improvement"
    return "FAIL -- Report is incomplete"
