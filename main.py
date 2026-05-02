"""
main.py — AutoBug AI v2 Entry Point

Pipeline:
  logs -> summarizer -> root_cause -> severity (with retry) -> fix -> final report

CLI:
  python main.py                 # interactive
  python main.py --sample        # bundled sample_logs.txt
  python main.py --file PATH     # custom log file
  python main.py --sample --no-eval   # skip evaluation
  python main.py --sample --quiet     # suppress agent logs
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from agents import summarizer_agent, root_cause_agent, severity_agent, report_agent
from evaluator import evaluate_report, print_evaluation

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).parent
SAMPLE_LOG = BASE_DIR / "sample_logs.txt"


# ---------------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------------

def run_pipeline(raw_logs: str) -> dict:
    """
    Run all 4 agents sequentially, passing outputs between them.
    Returns the final structured bug report dict (strict JSON schema).
    """
    print("\n" + "=" * 60)
    print("  >> PIPELINE START")
    print("=" * 60)

    # ── Agent 1: Summarizer ──────────────────────────────────────────────────
    _section("Agent 1 -- Summarizer")
    s_result = summarizer_agent(raw_logs)
    _show_result(s_result)

    # ── Agent 2: Root Cause ──────────────────────────────────────────────────
    _section("Agent 2 -- Root Cause Analyser")
    r_result = root_cause_agent(raw_logs, s_result["output"])
    _show_result(r_result)

    # ── Agent 3: Severity (with retry) ───────────────────────────────────────
    _section("Agent 3 -- Severity Classifier  [retry-enabled]")
    sev_result = severity_agent(raw_logs, s_result["output"], r_result["output"])
    _show_result(sev_result)

    # ── Agent 4: Fix / Report Generator ─────────────────────────────────────
    _section("Agent 4 -- Fix / Report Generator")
    fix_result = report_agent(
        raw_logs, s_result["output"], r_result["output"], sev_result["output"])
    _show_result(fix_result)

    # ── Compute overall confidence ───────────────────────────────────────────
    overall_confidence = round(
        (s_result["confidence"]
         + r_result["confidence"]
         + sev_result["confidence"]
         + fix_result["confidence"]) / 4,
        2,
    )

    report = {
        "summary":       s_result["output"],
        "root_cause":    r_result["output"],
        "severity":      sev_result["output"],
        "suggested_fix": fix_result["output"],
        "confidence":    overall_confidence,
    }
    return report


def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  >> {title}")
    print("=" * 60)


def _show_result(result: dict) -> None:
    preview = result["output"][:180].replace("\n", " ")
    suffix  = "..." if len(result["output"]) > 180 else ""
    print(f"  Output     : {preview}{suffix}")
    print(f"  Confidence : {result['confidence']:.2f}")


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------

def print_final_report(report: dict) -> None:
    print("\n" + "#" * 60)
    print("  [AutoBug AI v2] -- FINAL BUG REPORT")
    print("#" * 60)
    print(json.dumps(report, indent=2))
    print("#" * 60)


# ---------------------------------------------------------------------------
# LOG INPUT COLLECTION
# ---------------------------------------------------------------------------

def collect_logs(args: argparse.Namespace) -> str:
    """Return raw log text from --sample, --file, or interactive input."""

    if args.sample:
        if not SAMPLE_LOG.exists():
            logger.error("sample_logs.txt not found at: %s", SAMPLE_LOG)
            sys.exit(1)
        logger.info("Loading sample logs from: %s", SAMPLE_LOG)
        return SAMPLE_LOG.read_text(encoding="utf-8")

    if args.file:
        path = Path(args.file)
        if not path.exists():
            logger.error("File not found: %s", path)
            sys.exit(1)
        logger.info("Loading logs from file: %s", path)
        return path.read_text(encoding="utf-8")

    # Interactive mode
    print("\n" + "=" * 60)
    print("  [AutoBug AI v2] -- Automated Log Triage")
    print("=" * 60)
    print("\nOptions:")
    print("  [1]  Paste / type logs manually (blank line twice to submit)")
    print("  [2]  Use bundled sample_logs.txt")

    choice = input("\nEnter choice (1 or 2): ").strip()

    if choice == "2":
        if not SAMPLE_LOG.exists():
            logger.error("sample_logs.txt not found.")
            sys.exit(1)
        return SAMPLE_LOG.read_text(encoding="utf-8")

    print("\nPaste your logs below. Press ENTER twice when done:\n")
    lines: list = []
    try:
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
    except EOFError:
        pass

    raw_logs = "\n".join(lines).strip()
    if not raw_logs:
        logger.error("No log input provided. Exiting.")
        sys.exit(1)
    return raw_logs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autobug",
        description="AutoBug AI v2 — Multi-agent log triage system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py                       # interactive mode\n"
            "  python main.py --sample              # use bundled sample logs\n"
            "  python main.py --file app.log        # use a custom log file\n"
            "  python main.py --sample --no-eval    # skip evaluation\n"
            "  python main.py --sample --quiet      # suppress agent logs\n"
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--sample", action="store_true",
                       help="Run on the bundled sample_logs.txt")
    group.add_argument("--file", metavar="PATH",
                       help="Path to a custom log file")
    parser.add_argument("--no-eval", action="store_true",
                        help="Skip the evaluation step")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-agent logging")
    return parser


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    args = build_parser().parse_args()

    if args.quiet:
        logging.disable(logging.WARNING)

    raw_logs = collect_logs(args)
    logger.info("Input received: %d chars, %d lines.",
                len(raw_logs), raw_logs.count("\n") + 1)

    try:
        report = run_pipeline(raw_logs)
    except Exception as exc:
        logger.critical("Pipeline failed unexpectedly: %s", exc, exc_info=True)
        sys.exit(1)

    print_final_report(report)

    if not args.no_eval:
        score, checks = evaluate_report(report)
        print_evaluation(score, checks, report["confidence"])
    else:
        logger.info("Evaluation skipped (--no-eval).")


if __name__ == "__main__":
    main()
