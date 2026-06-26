# SUST CSE Carnival 2026

An automated AI/API SupportOps copilot designed to investigate digital finance complaints by reconciling customer text against transaction data.

## Tech Stack
- **Framework:** FastAPI
- **Validation:** Pydantic (v2)
- **Server:** Uvicorn
- **Logic:** Heuristic Rule-Based Reasoning (Regex + Signal Analysis)
- **Deployment:** Render / Docker

## AI Approach & Model Reasoning
This service utilizes a **Heuristic Reasoning Engine** rather than a heavy LLM. 
- **Why:** To ensure sub-100ms response times and 100% deterministic safety. In a financial context, hallucinations regarding transaction IDs or safety protocols (PIN/OTP) are high-risk.
- **Decision Logic:** The system extracts "signals" (Amounts, Transaction IDs, Phone Numbers) from the complaint using Regular Expressions and matches them against the provided history using a scoring algorithm.
- **Investigator Twist:** The `evidence_verdict` is determined by comparing the status of the matched transaction against keywords in the complaint (e.g., if a user reports a "failed" payment but the system sees it as "completed", it flags an `inconsistent` verdict).

## Safety Logic (Section 8 Compliance)
- **Credential Protection:** The system monitors for keywords like PIN, OTP, and Password. If detected, it automatically escalates to the `fraud_risk` department.
- **Refund Policy:** The `customer_reply` uses template-based responses that never confirm a refund, using authoritative but non-committal language as required ("under review," "through official channels").
- **Human Escalation:** All `inconsistent` verdicts, `phishing` cases, and high-value transactions (>10,000 BDT) are flagged with `human_review_required: true`.

## MODELS Section
- **Primary Logic:** Python Regex & Signal Matcher.
- **Reasoning:** Chosen for extreme reliability on CPU-only hardware (Render Free Tier) and to guarantee zero violations of FinTech safety rules.

## Setup and Installation

### Deployment URL
```
https://sust-preli-q40g.onrender.com/health
```

### Local Setup
1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
3. Run the server:
```
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Docker Setup
```
docker build -t queuestorm-investigator .
docker run -p 8000:8000 queuestorm-investigator
```
