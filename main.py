import re

from fastapi import FastAPI
from models import CaseType, Department,Department, EvidenceVerdict, Severity, TicketResponse, TicketRequest

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/analyze-ticket", response_model=TicketResponse)
def analyze_ticket(ticket: TicketRequest):

    # STEP 0: validate input
    if not ticket.complaint or not ticket.complaint.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Complaint text cannot be empty")

    if not ticket.ticket_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="ticket_id is required")

    # STEP 1: extract signals from complaint
    signals = extract_evidence_signals(ticket.complaint)

    # STEP 2: find best matching transaction
    trx = match_transaction(ticket, signals)

    # STEP 3: case type (FROM HISTORY ONLY as you decided)
    case_type = classify_case_type_from_history(ticket)

    # STEP 4: evidence check (complaint vs history)
    evidence = evaluate_evidence_verdict(ticket, trx, signals)

    # STEP 5: severity + department
    severity = compute_severity(case_type, evidence)
    department = map_department(case_type)

    # STEP 6: build outputs
    agent_summary = build_agent_summary(ticket, case_type, trx, signals)
    next_action = build_next_action(case_type)
    customer_reply = build_customer_reply(case_type)
    human_review = requires_human_review(case_type, evidence, trx, signals)

    # STEP 7: return response
    return TicketResponse(
        ticket_id=ticket.ticket_id,
        relevant_transaction_id=trx.transaction_id if trx else None,
        evidence_verdict=evidence,
        case_type=case_type,
        severity=severity,
        department=department,
        agent_summary=agent_summary,
        recommended_next_action=next_action,
        customer_reply=customer_reply,
        human_review_required=human_review,
        confidence= 0.8,
        reason_codes=[]
    )

# Utility functions
def extract_transaction_ids(complaint: str) -> list[str]:
    """
    Extract transaction IDs like TXN-9101 from the complaint.
    """

    pattern = r"\bTXN-\d+\b"
    return re.findall(pattern, complaint, flags=re.IGNORECASE)


def find_transaction_id(ticket: TicketRequest) -> str | None:
    """
    Return the matching transaction ID if the complaint explicitly
    mentions one that exists in the transaction history.
    """

    mentioned_ids = {
        tx.upper()
        for tx in extract_transaction_ids(ticket.complaint)
    }

    for trx in ticket.transaction_history:
        if trx.transaction_id.upper() in mentioned_ids:
            return trx.transaction_id

    return None




def compute_severity(case_type: CaseType, evidence_verdict: EvidenceVerdict) -> Severity:
    """
    Rule-based severity calculator.
    """

    # 1. If evidence is not strong → cap severity
    if evidence_verdict == EvidenceVerdict.insufficient_data:
        return Severity.low

    if evidence_verdict == EvidenceVerdict.inconsistent:
        return Severity.medium

    # 2. Now evidence is consistent → decide based on case_type
    if case_type == CaseType.phishing_or_social_engineering:
        return Severity.critical

    if case_type in [
        CaseType.wrong_transfer,
        CaseType.duplicate_payment
    ]:
        return Severity.high

    if case_type in [
        CaseType.payment_failed,
        CaseType.agent_cash_in_issue,
        CaseType.merchant_settlement_delay,
        CaseType.refund_request
    ]:
        return Severity.medium

    return Severity.low





def map_department(case_type: CaseType) -> Department:
    """
    Simple rule-based mapping from case_type → department.
    """

    mapping = {
        CaseType.wrong_transfer: Department.dispute_resolution,
        CaseType.refund_request: Department.dispute_resolution,

        CaseType.payment_failed: Department.payments_ops,
        CaseType.duplicate_payment: Department.payments_ops,

        CaseType.merchant_settlement_delay: Department.merchant_operations,

        CaseType.agent_cash_in_issue: Department.agent_operations,

        CaseType.phishing_or_social_engineering: Department.fraud_risk,

        CaseType.other: Department.customer_support,
    }

    return mapping.get(case_type, Department.customer_support)


def classify_case_type_from_history(ticket):
    """
    Case type derived from transaction history AND complaint signals.
    """
    history = ticket.transaction_history
    complaint_lower = ticket.complaint.lower() if ticket.complaint else ""

    # 1. PHISHING (check complaint first - critical safety)
    phishing_keywords = ["pin", "otp", "password", "scam", "fraud", "phishing",
                         "someone calling", "asked for my", "share my pin",
                         "fake call", "block my account"]
    if any(k in complaint_lower for k in phishing_keywords):
        return CaseType.phishing_or_social_engineering

    if not history:
        # No history - rely on complaint keywords
        if any(k in complaint_lower for k in ["refund", "return my money"]):
            return CaseType.refund_request
        if any(k in complaint_lower for k in ["settlement", "merchant"]):
            return CaseType.merchant_settlement_delay
        if any(k in complaint_lower for k in ["agent", "cash in", "deposited", "cash-in"]):
            return CaseType.agent_cash_in_issue
        if any(k in complaint_lower for k in ["wrong", "wrong number", "wrong person"]):
            return CaseType.wrong_transfer
        return CaseType.other

    # 1. PAYMENT FAILED
    for trx in history:
        if trx.status == "failed":
            return CaseType.payment_failed

    # 2. REFUND (check history or complaint)
    for trx in history:
        if trx.type == "refund":
            return CaseType.refund_request
    if "refund" in complaint_lower:
        return CaseType.refund_request

    # 3. CASH IN ISSUE
    for trx in history:
        if trx.type == "cash_in" and trx.status != "completed":
            return CaseType.agent_cash_in_issue
    if any(k in complaint_lower for k in ["agent", "cash in", "deposited"]):
        return CaseType.agent_cash_in_issue

    # 4. SETTLEMENT DELAY
    for trx in history:
        if trx.type == "settlement" and trx.status != "completed":
            return CaseType.merchant_settlement_delay
    if "settlement" in complaint_lower:
        return CaseType.merchant_settlement_delay

    # 5. DUPLICATE PAYMENT (simple version)
    amounts = [trx.amount for trx in history]
    if len(amounts) != len(set(amounts)):
        return CaseType.duplicate_payment

    # 6. TRANSFER DEFAULT
    for trx in history:
        if trx.type == "transfer":
            return CaseType.wrong_transfer

    return CaseType.other



# for evidence verdict

def extract_evidence_signals(text: str):
    text_lower = text.lower()

    # 1. amount (simple)
    amounts = re.findall(r"\b\d+(?:\.\d+)?\b", text_lower)
    amounts = [float(a) for a in amounts]

    # 2. possible phone numbers / IDs (very loose)
    phone_like = re.findall(r"\+?\d{10,13}", text)

    # 3. transaction id
    txn_ids = re.findall(r"\bTXN-\d+\b", text.upper())

    # 4. keywords
    keywords = {
        "failed": "failed",
        "not sent": "not_sent",
        "wrong": "wrong",
        "refund": "refund",
        "cash in": "cash_in",
        "settlement": "settlement",
        "pin": "pin",
        "otp": "otp",
        "password": "password",
    }

    found_keywords = [k for k in keywords if k in text_lower]

    return {
        "amounts": amounts,
        "phones": phone_like,
        "txn_ids": txn_ids,
        "keywords": found_keywords
    }



def match_transaction(ticket, signals):
    """
    Try to find best matching transaction.
    Returns matched trx or None.
    """

    best_match = None
    best_score = 0

    for trx in ticket.transaction_history:
        score = 0

        # 1. transaction ID match (strongest)
        if signals["txn_ids"]:
            if trx.transaction_id.upper() in signals["txn_ids"]:
                score += 5

        # 2. amount match
        if trx.amount in signals["amounts"]:
            score += 3

        # 3. counterparty match
        if any(p in trx.counterparty for p in signals["phones"]):
            score += 3

        # 4. weak keyword hint
        if "wrong" in signals["keywords"] and trx.type == "transfer":
            score += 1

        if score > best_score:
            best_score = score
            best_match = trx

    # threshold: must be somewhat confident
    if best_score >= 3:
        return best_match

    return None



def evaluate_evidence_verdict(ticket, trx, signals):
    """
    Evaluate whether the complaint evidence is consistent with transaction history.
    """
    # 1. no transaction found
    if trx is None:
        return EvidenceVerdict.insufficient_data

    complaint_lower = ticket.complaint.lower()
    kw = signals["keywords"]

    # 2. contradiction: complaint says failed but trx is completed
    if "failed" in kw and trx.status == "completed":
        return EvidenceVerdict.inconsistent

    # 3. contradiction: amount mismatch (complaint amount differs from trx amount)
    if signals["amounts"] and trx.amount not in signals["amounts"]:
        return EvidenceVerdict.inconsistent

    # 4. contradiction: complaint says wrong transfer but trx is not a transfer
    if "wrong" in kw and trx.type != "transfer":
        return EvidenceVerdict.inconsistent

    # 5. strong match
    if (
        trx.amount in signals["amounts"]
        or trx.transaction_id.upper() in signals["txn_ids"]
    ):
        return EvidenceVerdict.consistent

    # 6. default safe case
    return EvidenceVerdict.insufficient_data

#evidence verdict ends



def build_agent_summary(ticket, case_type, trx, signals):
    """
    One to two sentence internal summary.
    """

    summary = f"""
Ticket {ticket.ticket_id} reported as {case_type.value}.
"""

    if trx:
        summary += f" Relevant transaction: {trx.transaction_id}, amount {trx.amount}, status {trx.status}."
    else:
        summary += " No matching transaction found in history."

    if signals["amounts"]:
        summary += f" Reported amount: {signals['amounts'][0]}."

    return summary.strip()



def build_next_action(case_type):

    if case_type == CaseType.refund_request:
        return "Route case to Refunds Team for processing."

    if case_type == CaseType.wrong_transfer:
        return "Verify transaction details and initiate beneficiary confirmation process."

    if case_type == CaseType.payment_failed:
        return "Check payment gateway logs and transaction status."

    if case_type == CaseType.duplicate_payment:
        return "Start reconciliation for duplicate transaction detection."

    if case_type == CaseType.merchant_settlement_delay:
        return "Escalate to Merchant Operations for settlement review."

    if case_type == CaseType.agent_cash_in_issue:
        return "Investigate agent cash-in ledger mismatch."

    if case_type == CaseType.phishing_or_social_engineering:
        return "Escalate immediately to Fraud Risk team."

    return "Perform standard case review and validation."


def build_customer_reply(case_type):

    if case_type == CaseType.refund_request:
        return "We have received your refund request and it is under review. If eligible, the amount will be processed through official channels."

    if case_type == CaseType.wrong_transfer:
        return "We are reviewing your transaction details. If any discrepancy is found, it will be handled through official support procedures."

    if case_type == CaseType.payment_failed:
        return "We are checking the status of your payment. Please wait while we verify the transaction."

    if case_type == CaseType.phishing_or_social_engineering:
        return "For your safety, we are reviewing this case urgently. Please do not share sensitive information with anyone."

    if case_type == CaseType.merchant_settlement_delay:
        return "We are reviewing your settlement query. Our merchant operations team will follow up with you shortly."

    if case_type == CaseType.agent_cash_in_issue:
        return "We are investigating your cash-in issue. Please allow us some time to verify with the agent."

    if case_type == CaseType.duplicate_payment:
        return "We have noted your concern about a possible duplicate payment. Our team will review and update you."

    return "Your complaint has been received and is under review. We will update you after verification."


def requires_human_review(case_type, evidence, trx, signals):

    # fraud always
    if case_type == CaseType.phishing_or_social_engineering:
        return True

    # inconsistent evidence
    if evidence == EvidenceVerdict.inconsistent:
        return True

    # no transaction match
    if trx is None:
        return True

    # high value check
    if signals["amounts"] and max(signals["amounts"]) > 10000:
        return True

    # wrong transfer is sensitive
    if case_type == CaseType.wrong_transfer:
        return True

    return False