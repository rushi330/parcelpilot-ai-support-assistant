"""Deterministic intent classification and entity extraction.

No LLM call happens here at all - this is plain regex/keyword logic, which is
what makes the rest of the pipeline able to get away with exactly one LLM
call per turn (the orchestrator only calls the LLM once it already knows
what the customer wants and has gathered the evidence for it).
"""
import re

ORDER_ID_RE = re.compile(r"\bORD-\d+\b", re.IGNORECASE)
TICKET_ID_RE = re.compile(r"\bTKT-\d+\b", re.IGNORECASE)
KI_ID_RE = re.compile(r"\bKI-\d+\b", re.IGNORECASE)
SEVERITY_RE = re.compile(r"\bP[123]\b", re.IGNORECASE)

FOLLOWUP_REFERENCE_WORDS = (
    "it", "that order", "this order", "the order", "that shipment",
    "this shipment", "the shipment", "that ticket", "this ticket", "the ticket",
)

# Intent keyword sets, checked in priority order (most specific first).
_ESCALATE_KW = ("escalate", "escalation", "speak to someone", "talk to a human",
                 "raise this", "human agent")
_CANCEL_KW = ("cancel",)
_CREDIT_KW = ("credit", "compensat", "reimburse")
_SLA_KW = ("sla", "response time", "how long will", "breach", "first response")
_ORDER_STATUS_KW = ("status of", "where is my order", "track my order", "order status")
_LIST_ORDERS_KW = ("my orders", "all my orders", "list my orders")
_TICKET_STATUS_KW = ("ticket status", "status of my ticket", "status of ticket")
_LIST_TICKETS_KW = ("my tickets", "all my tickets", "list my tickets")
_ACCOUNT_KW = ("my plan", "my account", "premium support", "account status")

_AFFIRMATIVE_RE = re.compile(
    r"^\s*(yes|yep|yeah|yup|confirm|confirmed|proceed|go ahead|do it|please do|sure|ok(ay)?)\b",
    re.IGNORECASE,
)
_NEGATIVE_RE = re.compile(
    r"^\s*(no|nope|nah|cancel|don'?t|do not|never\s?mind|stop|hold off)\b",
    re.IGNORECASE,
)


def extract_entities(message: str) -> dict:
    return {
        "order_ids": [m.upper() for m in ORDER_ID_RE.findall(message)],
        "ticket_ids": [m.upper() for m in TICKET_ID_RE.findall(message)],
        "ki_ids": [m.upper() for m in KI_ID_RE.findall(message)],
        "severity": (SEVERITY_RE.findall(message) or [None])[0],
        "has_followup_reference": any(w in message.lower() for w in FOLLOWUP_REFERENCE_WORDS),
    }


def classify_intent(message: str) -> str:
    """Returns one of: escalate, cancellation, service_credit, sla,
    order_status, list_orders, ticket_status, list_tickets, account_info,
    general."""
    m = message.lower()

    if any(k in m for k in _ESCALATE_KW):
        return "escalate"
    if any(k in m for k in _CANCEL_KW):
        return "cancellation"
    if any(k in m for k in _CREDIT_KW):
        return "service_credit"
    if any(k in m for k in _SLA_KW):
        return "sla"
    if any(k in m for k in _LIST_ORDERS_KW):
        return "list_orders"
    if any(k in m for k in _ORDER_STATUS_KW):
        return "order_status"
    if any(k in m for k in _LIST_TICKETS_KW):
        return "list_tickets"
    if any(k in m for k in _TICKET_STATUS_KW):
        return "ticket_status"
    if any(k in m for k in _ACCOUNT_KW):
        return "account_info"
    return "general"


def classify_confirmation(message: str) -> str:
    """For turns where a pending action exists. Returns 'affirmative',
    'negative', or 'ambiguous'."""
    if _AFFIRMATIVE_RE.match(message.strip()):
        return "affirmative"
    if _NEGATIVE_RE.match(message.strip()):
        return "negative"
    return "ambiguous"
