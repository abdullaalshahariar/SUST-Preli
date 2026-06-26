from fastapi import FastAPI
from models import CaseType, Department,Department, EvidenceVerdict, Severity, TicketResponse, TicketRequest

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/analyze-ticket", response_model=TicketResponse)
def analyze_ticket(ticket: TicketRequest):
        response = TicketResponse(
            ticket_id=ticket.ticket_id,
            relevant_transaction_id=None,
            evidence_verdict=EvidenceVerdict.insufficient_data,
            case_type=CaseType.other,
            severity=Severity.low,
            department=Department.customer_support,
            agent_summary="Dummy summary",
            recommended_next_action="Dummy action",
            customer_reply="Dummy reply",
            human_review_required=False,
            confidence=0.5,
            reason_codes=[]
        )
        return response