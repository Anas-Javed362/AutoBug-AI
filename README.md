# AutoBug AI 🐛🤖

**A multi-agent LLM-based system for automated log analysis and bug triage.**

AutoBug AI ingests raw system logs or error messages and produces a structured JSON bug report — automatically summarised, root-cause analysed, severity-classified, and fix-suggested — by chaining four specialised AI agents.

---

## Table of Contents
1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Running the Project](#running-the-project)
5. [Example Input / Output](#example-input--output)
6. [Evaluation System](#evaluation-system)
7. [Configuration](#configuration)
8. [Design Decisions](#design-decisions)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    AutoBug AI Pipeline                   │
│                                                         │
│  ┌─────────────┐                                        │
│  │  Raw Logs   │  (string or file input via CLI)        │
│  └──────┬──────┘                                        │
│         │                                               │
│         ▼                                               │
│  ┌─────────────────────┐                                │
│  │  Agent 1            │                                │
│  │  SummarizerAgent    │ → Concise natural-language     │
│  │                     │   summary of the log events    │
│  └──────────┬──────────┘                                │
│             │ summary                                   │
│             ▼                                           │
│  ┌─────────────────────┐                                │
│  │  Agent 2            │                                │
│  │  RootCauseAgent     │ → Identifies the single most  │
│  │                     │   likely root cause            │
│  └──────────┬──────────┘                                │
│             │ root_cause                                │
│             ▼                                           │
│  ┌─────────────────────┐                                │
│  │  Agent 3            │                                │
│  │  SeverityAgent      │ → Classifies as one of:       │
│  │                     │   Low / Medium / High /        │
│  │                     │   Critical                     │
│  └──────────┬──────────┘                                │
│             │ severity                                  │
│             ▼                                           │
│  ┌─────────────────────┐                                │
│  │  Agent 4            │                                │
│  │  ReportAgent        │ → Combines all outputs into   │
│  │                     │   structured JSON bug report  │
│  └──────────┬──────────┘                                │
│             │                                           │
│             ▼                                           │
│  ┌─────────────────────┐                                │
│  │  Evaluator          │ → Scores report quality 0–1   │
│  └─────────────────────┘                                │
└─────────────────────────────────────────────────────────┘
```

### Agent Collaboration
Each agent **receives the outputs of all previous agents** as context, simulating a collaborative triage process:

| Agent | Inputs | Output |
|-------|--------|--------|
| SummarizerAgent | raw_logs | summary |
| RootCauseAgent | raw_logs + summary | root_cause |
| SeverityAgent | raw_logs + summary + root_cause | severity |
| ReportAgent | raw_logs + summary + root_cause + severity | bug report JSON |

### LLM Backend Strategy
- **With `OPENAI_API_KEY`** → calls `gpt-3.5-turbo` via the OpenAI Python SDK.
- **Without API key** → falls back to a heuristic mock that inspects log keywords to produce realistic responses. The full pipeline runs without any API key.

---

## Project Structure

```
AutoBugAI/
├── main.py          ← CLI entry point & pipeline orchestration
├── agents.py        ← All 4 agents + LLM backend (OpenAI / mock)
├── evaluator.py     ← Report evaluation & scoring
├── sample_logs.txt  ← Realistic sample system logs
└── README.md        ← This file
```

---

## Installation

```bash
# 1. Clone / navigate to the project directory
cd AutoBugAI

# 2. (Recommended) Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install openai            # Only needed for real LLM calls
# No other external dependencies — stdlib only for mock mode
```

---

## Running the Project

### Interactive mode (paste logs or choose sample)
```bash
python main.py
```

### Use bundled sample logs
```bash
python main.py --sample
```

### Analyse a custom log file
```bash
python main.py --file path/to/your/app.log
```

### Skip evaluation output
```bash
python main.py --sample --no-eval
```

### Suppress agent step logs (quiet mode)
```bash
python main.py --sample --quiet
```

### Using OpenAI (real LLM calls)
```bash
set OPENAI_API_KEY=sk-...       # Windows
# export OPENAI_API_KEY=sk-...  # macOS / Linux
python main.py --sample
```

---

## Example Input / Output

### Input (`sample_logs.txt`)
```
2024-01-15 03:12:45 ERROR [database] Connection pool exhausted: max_connections=50 reached
2024-01-15 03:12:45 ERROR [database] Failed to acquire connection after 30s timeout
2024-01-15 03:12:46 ERROR [api-gateway] Upstream service timeout: /api/v1/orders → 504
2024-01-15 03:12:48 CRITICAL [api-gateway] All retries exhausted. Returning 503 to client.
2024-01-15 03:12:50 ERROR [order-service] NullPointerException in OrderProcessor.processOrder()
2024-01-15 03:12:56 CRITICAL [system] Memory usage at 97%: heap_used=3.8GB/4GB
2024-01-15 03:13:00 CRITICAL [system] OOM Killer invoked — process 'order-service' terminated
```

### Final Output (JSON)
```json
{
  "summary": "System logs show a cascading failure beginning with database connection pool
              exhaustion. The API gateway began timing out (504/503), the order service
              threw NullPointerExceptions, and memory pressure reached 97%, causing the
              OOM Killer to terminate the order-service process.",

  "root_cause": "Root cause: Database connection pool exhausted (max connections=50 reached).
                 This triggered a cascade — API gateway timeouts, NullPointerExceptions in
                 the order service (order=null due to failed DB fetch), Redis cache misses
                 spiking to 94%, and ultimately OOM termination of the order-service.",

  "severity": "Critical",

  "suggested_fix": "1. Increase DB connection pool size (e.g. max_connections=200) and
                       add connection timeout tuning.\n
                    2. Implement a circuit breaker on the API gateway to fail fast
                       instead of cascading retries.\n
                    3. Add a null-check guard in OrderProcessor.processOrder() before
                       calling order.getItems().\n
                    4. Increase JVM heap allocation or add horizontal pod autoscaling
                       to handle memory pressure.\n
                    5. Add alerting at 75% memory/connection thresholds for early
                       warning before cascade failure."
}
```

### Evaluation Output
```
════════════════════════════════════════════════════════════
  📊  EVALUATION REPORT
════════════════════════════════════════════════════════════
  Score : 1.00 / 1.00   [████████████████████]
  Grade : PASS — Excellent ✨
────────────────────────────────────────────────────────────
  ✅  All Fields Present
       → All required fields found.
  ✅  Severity Valid
       → Severity 'Critical' is a valid classification.
  ✅  Summary Detailed
       → Summary has 214 characters (minimum 30).
  ✅  Root And Fix Detailed
       → root_cause=312 chars, suggested_fix=498 chars (both >= 20).
════════════════════════════════════════════════════════════
```

---

## Evaluation System

The evaluator scores each generated report on 4 equally-weighted checks:

| Check | Weight | Criterion |
|-------|--------|-----------|
| All fields present | 0.25 | `summary`, `root_cause`, `severity`, `suggested_fix` all non-empty |
| Severity valid | 0.25 | Value must be one of: `Low`, `Medium`, `High`, `Critical` |
| Summary detailed | 0.25 | Summary ≥ 30 characters |
| Root cause & fix detailed | 0.25 | Both ≥ 20 characters |

**Final score = (checks passed) / 4**

---

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `OPENAI_API_KEY` | *(unset)* | Set to enable real LLM calls. Falls back to mock if absent. |

---

## Design Decisions

- **No external dependencies beyond `openai`** — the system works fully offline with the heuristic mock.
- **Sequential pipeline** — each agent's output enriches the next agent's context, mimicking real triage collaboration.
- **Graceful degradation** — if any LLM call fails or returns garbage, agents fall back to safe defaults rather than crashing.
- **Separation of concerns** — agents, evaluation, and CLI are in separate modules; `main.py` is purely orchestration.
- **Type hints throughout** — all public functions are fully typed for clarity and IDE support.
