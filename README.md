# AutoBug AI 🐛🤖

**A multi-agent LLM-based system for automated log analysis and bug triage.**

AutoBug AI ingests raw system logs or error messages and produces a structured JSON bug report — automatically summarised, root-cause analysed, severity-classified, and fix-suggested — by chaining four specialised AI agents.

---

## 📑 Table of Contents
1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Running the Project](#running-the-project)
5. [Example Input / Output](#example-input--output)
6. [Evaluation System](#evaluation-system)
7. [Configuration](#configuration)
8. [Design Decisions](#design-decisions)

---

## 🏗️ Architecture


┌─────────────────────────────────────────────────────────┐
│ AutoBug AI Pipeline │
│ │
│ ┌─────────────┐ │
│ │ Raw Logs │ (CLI input) │
│ └──────┬──────┘ │
│ ▼ │
│ ┌─────────────────────┐ │
│ │ SummarizerAgent │ → Log summary │
│ └──────────┬──────────┘ │
│ ▼ │
│ ┌─────────────────────┐ │
│ │ RootCauseAgent │ → Root cause │
│ └──────────┬──────────┘ │
│ ▼ │
│ ┌─────────────────────┐ │
│ │ SeverityAgent │ → Low/Medium/High/Critical │
│ └──────────┬──────────┘ │
│ ▼ │
│ ┌─────────────────────┐ │
│ │ ReportAgent │ → Final JSON report │
│ └──────────┬──────────┘ │
│ ▼ │
│ ┌─────────────────────┐ │
│ │ Evaluator │ → Score (0–1) │
│ └─────────────────────┘ │
└─────────────────────────────────────────────────────────┘


---

### 🤝 Agent Collaboration

| Agent | Inputs | Output |
|------|--------|--------|
| SummarizerAgent | raw_logs | summary |
| RootCauseAgent | raw_logs + summary | root_cause |
| SeverityAgent | raw_logs + summary + root_cause | severity |
| ReportAgent | all previous outputs | structured JSON |

---

### ⚙️ LLM Backend Strategy

- With `OPENAI_API_KEY` → Uses OpenAI API  
- Without API key → Uses fallback heuristic mock (fully offline support)

---

## 📁 Project Structure


AutoBugAI/
├── main.py
├── agents.py
├── evaluator.py
├── sample_logs.txt
└── README.md


---

## ⚙️ Installation

```bash
# Navigate to project
cd AutoBugAI

# Create virtual environment
python -m venv venv

# Activate
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependency
pip install openai
🚀 Running the Project
Interactive Mode
python main.py
Run Sample Logs
python main.py --sample
Run Custom Log File
python main.py --file path/to/log.txt
Disable Evaluation
python main.py --sample --no-eval
Quiet Mode
python main.py --sample --quiet
📊 Example Input / Output
Input
ERROR database connection failed
CRITICAL memory usage 97%
Output (JSON)
{
  "summary": "System failure due to DB exhaustion...",
  "root_cause": "Database connection pool limit reached",
  "severity": "Critical",
  "suggested_fix": "Increase pool size, optimize queries"
}
📈 Evaluation System
Check	Weight	Requirement
Fields present	0.25	All fields exist
Severity valid	0.25	Must be valid category
Summary length	0.25	≥ 30 chars
Root & Fix length	0.25	≥ 20 chars

Final Score = Passed Checks / 4

🔧 Configuration
Variable	Description
OPENAI_API_KEY	Enables real LLM usage
