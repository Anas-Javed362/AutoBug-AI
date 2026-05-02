"""
agents.py — AutoBug AI v2

Each agent returns: {"output": str, "confidence": float (0.0-1.0)}

Agents:
  1. summarizer_agent   → concise log summary
  2. root_cause_agent   → identifies root cause
  3. severity_agent     → classifies severity WITH retry logic (up to 2 retries)
  4. report_agent       → produces suggested fix
"""

import os
import random
import logging
from typing import TypedDict

logger = logging.getLogger(__name__)

VALID_SEVERITIES = {"Low", "Medium", "High", "Critical"}
MAX_SEVERITY_RETRIES = 2

# ---------------------------------------------------------------------------
# Agent Result Type
# ---------------------------------------------------------------------------

class AgentResult(TypedDict):
    output: str
    confidence: float


# ---------------------------------------------------------------------------
# LLM BACKEND
# ---------------------------------------------------------------------------

def call_llm(prompt: str, context: str = "") -> str:
    """Route to OpenAI API if key is set, else fall back to mock."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        return _call_openai(prompt, context, api_key)
    logger.warning("OPENAI_API_KEY not set — using heuristic mock LLM.")
    return _mock_llm(prompt, context)


def _call_openai(prompt: str, context: str, api_key: str) -> str:
    try:
        import openai  # type: ignore
        client = openai.OpenAI(api_key=api_key)
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.2,
            max_tokens=512,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("OpenAI call failed: %s — falling back to mock.", exc)
        return _mock_llm(prompt, context)


# Track severity call count so mock triggers one bad response to test retry
_severity_call_count = 0


def _mock_llm(prompt: str, context: str) -> str:
    """
    Heuristic mock. Uses TASK: tags in prompts to dispatch cleanly.
    Deliberately returns an invalid severity on the FIRST call to test retry.
    """
    global _severity_call_count

    # --- TASK:SUMMARIZE ---
    if "TASK:SUMMARIZE" in prompt:
        lines = context.splitlines() if context else []
        error_lines = [ln for ln in lines if any(
            k in ln.upper() for k in ["ERROR", "CRITICAL", "WARN"])]
        if error_lines:
            first_crit = next(
                (ln for ln in error_lines if "CRITICAL" in ln.upper()), error_lines[0])
            return (
                "System logs reveal a cascading failure originating in the database tier. "
                "The connection pool reached its limit (max_connections=50), causing the "
                "API gateway to return 504/503 errors after all retries were exhausted. "
                "The order-service threw NullPointerExceptions and was eventually terminated "
                f"by the OOM Killer as heap usage hit 97%. "
                f"First critical event: '{first_crit.strip()[:90]}'. "
                f"Total anomalous log lines: {len(error_lines)}."
            )
        return "Logs contain no critical errors. System appears fully operational."

    # --- TASK:ROOT_CAUSE ---
    if "TASK:ROOT_CAUSE" in prompt:
        combined = (prompt + context).lower()
        if "connection pool" in combined or "max_connections" in combined:
            return (
                "Root cause: The database connection pool was exhausted (max_connections=50). "
                "With no available DB connections, the order-service could not fetch order "
                "data, causing order objects to be null and triggering NullPointerExceptions. "
                "The API gateway cascaded into 504/503 errors across all retries, and the "
                "resulting memory pressure led to OOM termination of the order-service process."
            )
        if "nullpointer" in combined or "null" in combined:
            return (
                "Root cause: NullPointerException in OrderProcessor.processOrder() — "
                "an Order object was null because the database query returned no result, "
                "likely due to upstream connection failures."
            )
        return (
            "Root cause could not be determined automatically. "
            "Manual investigation of the stack trace is required."
        )

    # --- TASK:SEVERITY ---
    if "TASK:SEVERITY" in prompt:
        _severity_call_count += 1
        # Deliberately return invalid on first call to demonstrate retry logic
        if _severity_call_count == 1:
            logger.debug("[Mock] Simulating bad severity on attempt 1 to trigger retry...")
            return "SEVERE"  # Invalid — not in {"Low","Medium","High","Critical"}
        combined = (prompt + context).lower()
        if "critical" in combined or "oom" in combined or "terminated" in combined:
            return "Critical"
        if "error" in combined and "warn" in combined:
            return "High"
        if "error" in combined:
            return "Medium"
        return "Low"

    # --- TASK:SUGGESTED_FIX ---
    if "TASK:SUGGESTED_FIX" in prompt:
        combined = (prompt + context).lower()
        if "connection pool" in combined or "database" in combined:
            return (
                "1. Increase the database connection pool size (e.g. max_connections=200) "
                "and tune acquisition timeout settings.\n"
                "2. Implement a circuit breaker on the API gateway to fail fast instead of "
                "exhausting retries when the upstream is down.\n"
                "3. Add a null-check guard in OrderProcessor.processOrder() before calling "
                "order.getItems() to prevent NullPointerExceptions.\n"
                "4. Tune JVM heap allocation (-Xmx) or enable horizontal pod autoscaling "
                "to handle memory pressure.\n"
                "5. Set up alerting at 75% connection pool utilisation and 80% memory usage "
                "to catch issues before they cascade into outages."
            )
        return (
            "1. Identify and fix the root cause component.\n"
            "2. Add proper null-checks and error handling.\n"
            "3. Implement resource limits and circuit breakers.\n"
            "4. Add monitoring and alerting for early detection.\n"
            "5. Load-test the fix before deploying to production."
        )

    return "Unable to determine a response — please provide more context."


# ---------------------------------------------------------------------------
# CONFIDENCE HELPER
# ---------------------------------------------------------------------------

def _compute_confidence(output: str, keywords: list, min_len: int = 60) -> float:
    """
    Compute a realistic confidence score based on:
      - output length (up to 0.5)
      - keyword presence (up to 0.4)
      - small random jitter (+-0.05)
    """
    if not output or len(output.strip()) < 10:
        return 0.1

    length_score = min(len(output.strip()) / (min_len * 4), 0.5)
    keyword_score = 0.0
    if keywords:
        hits = sum(1 for kw in keywords if kw.lower() in output.lower())
        keyword_score = min(hits / len(keywords), 1.0) * 0.4
    else:
        keyword_score = 0.3

    jitter = random.uniform(-0.05, 0.05)
    score = max(0.1, min(1.0, round(length_score + keyword_score + jitter + 0.1, 2)))
    return score


# ---------------------------------------------------------------------------
# AGENT 1 — SUMMARIZER
# ---------------------------------------------------------------------------

def summarizer_agent(raw_logs: str) -> AgentResult:
    logger.info("Running Summarizer...")
    prompt = (
        "TASK:SUMMARIZE\n"
        "You are a senior SRE. Analyze the system logs and write a concise 2-4 sentence "
        "summary focusing on errors and critical events. Do NOT list every line.\n\n"
        f"LOGS:\n{raw_logs}\n\nSUMMARY:"
    )
    try:
        output = call_llm(prompt, context=raw_logs)
        if not output or len(output.strip()) < 10:
            raise ValueError("Response too short")
    except Exception as exc:
        logger.warning("[SummarizerAgent] Failed (%s) — using fallback.", exc)
        output = "Log analysis failed. Raw logs require manual review."

    confidence = _compute_confidence(
        output,
        keywords=["error", "critical", "failure", "connection", "service", "terminated"],
        min_len=80,
    )
    logger.info("[SummarizerAgent] Done. Confidence: %.2f", confidence)
    return {"output": output.strip(), "confidence": confidence}


# ---------------------------------------------------------------------------
# AGENT 2 — ROOT CAUSE
# ---------------------------------------------------------------------------

def root_cause_agent(raw_logs: str, summary: str) -> AgentResult:
    logger.info("Running Root Cause Analyser...")
    prompt = (
        "TASK:ROOT_CAUSE\n"
        "You are a backend debugging expert. Identify the single most likely ROOT CAUSE "
        "of the failure. Be specific — mention component, error type, and the chain. "
        "Keep to 2-3 sentences.\n\n"
        f"SUMMARY:\n{summary}\n\nRAW LOGS:\n{raw_logs}\n\nROOT CAUSE:"
    )
    try:
        output = call_llm(prompt, context=raw_logs)
        if not output or len(output.strip()) < 10:
            raise ValueError("Response too short")
    except Exception as exc:
        logger.warning("[RootCauseAgent] Failed (%s) — using fallback.", exc)
        output = "Root cause could not be determined. Manual investigation required."

    confidence = _compute_confidence(
        output,
        keywords=["root cause", "exhausted", "null", "failed", "connection", "oom", "cascade"],
        min_len=60,
    )
    logger.info("[RootCauseAgent] Done. Confidence: %.2f", confidence)
    return {"output": output.strip(), "confidence": confidence}


# ---------------------------------------------------------------------------
# AGENT 3 — SEVERITY (with retry logic)
# ---------------------------------------------------------------------------

def severity_agent(raw_logs: str, summary: str, root_cause: str) -> AgentResult:
    logger.info("Running Severity Classifier...")

    def _build_prompt() -> str:
        return (
            "TASK:SEVERITY\n"
            "You are an incident manager. Classify the severity as EXACTLY one of: "
            "Low, Medium, High, Critical.\n"
            "  Critical -- system down, OOM, cascading failures, data loss\n"
            "  High     -- major feature broken, many users affected\n"
            "  Medium   -- partial degradation, non-critical service affected\n"
            "  Low      -- minor warnings, no user impact\n\n"
            f"SUMMARY:\n{summary}\n\nROOT CAUSE:\n{root_cause}\n\n"
            "Respond with ONLY the severity word:\nSEVERITY:"
        )

    severity = None
    confidence = 0.0
    attempt = 0

    while attempt <= MAX_SEVERITY_RETRIES:
        if attempt > 0:
            logger.warning(
                "[SeverityAgent] Retry attempt %d/%d — previous output was invalid.",
                attempt, MAX_SEVERITY_RETRIES,
            )
        try:
            response = call_llm(_build_prompt(), context=raw_logs)
            parsed = _extract_severity(response)
            if parsed:
                severity = parsed
                # Confidence decreases slightly with each retry
                base = 0.90 - (attempt * 0.10)
                confidence = round(
                    max(0.3, min(1.0, base + random.uniform(-0.05, 0.05))), 2)
                logger.info(
                    "[SeverityAgent] Valid severity '%s' on attempt %d. Confidence: %.2f",
                    severity, attempt + 1, confidence,
                )
                break
            else:
                logger.warning(
                    "[SeverityAgent] Attempt %d: invalid response '%s'",
                    attempt + 1, response.strip()[:40],
                )
        except Exception as exc:
            logger.error("[SeverityAgent] Attempt %d error: %s", attempt + 1, exc)

        attempt += 1

    if severity is None:
        logger.warning(
            "[SeverityAgent] All %d retries exhausted — falling back to 'Medium' with low confidence.",
            MAX_SEVERITY_RETRIES,
        )
        severity = "Medium"
        confidence = 0.30  # low confidence signals the fallback

    return {"output": severity, "confidence": confidence}


def _extract_severity(response: str) -> str:
    """Return a valid severity string if found in response, else empty string."""
    for level in VALID_SEVERITIES:
        if level.lower() in response.lower():
            return level
    return ""


# ---------------------------------------------------------------------------
# AGENT 4 — FIX / REPORT GENERATOR
# ---------------------------------------------------------------------------

def report_agent(
    raw_logs: str,
    summary: str,
    root_cause: str,
    severity: str,
) -> AgentResult:
    logger.info("Running Fix / Report Generator...")
    prompt = (
        "TASK:SUGGESTED_FIX\n"
        "You are a senior engineer writing a triage report. "
        "Write a numbered list of 3-5 actionable fix steps.\n\n"
        f"SUMMARY:\n{summary}\n\nROOT CAUSE:\n{root_cause}\n\nSEVERITY: {severity}\n\n"
        "SUGGESTED FIX:"
    )
    try:
        output = call_llm(prompt, context=raw_logs)
        if not output or len(output.strip()) < 10:
            raise ValueError("Response too short")
    except Exception as exc:
        logger.warning("[ReportAgent] Failed (%s) — using fallback.", exc)
        output = (
            "1. Review the stack trace and identify the failing component.\n"
            "2. Check resource limits (DB connections, memory, threads).\n"
            "3. Add error handling and null-checks.\n"
            "4. Implement circuit breakers to prevent cascades.\n"
            "5. Set up alerts for early detection."
        )

    confidence = _compute_confidence(
        output,
        keywords=["increase", "implement", "add", "fix", "check", "alert", "null-check"],
        min_len=100,
    )
    logger.info("[ReportAgent] Done. Confidence: %.2f", confidence)
    return {"output": output.strip(), "confidence": confidence}
