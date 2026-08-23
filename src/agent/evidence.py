"""Builds a verified evidence package for a given intent + entities, using
only deterministic lookups/calculations and semantic retrieval - no LLM calls.

The orchestrator hands this package (and only this package) to the LLM for
natural-language synthesis. If a field would be missing/unknown, it stays
missing/unknown in the package rather than being guessed here - the LLM is
instructed never to fill gaps, and the package makes gaps explicit instead
of glossing over them.
"""
from src.data.account_tools import lookup_account
from src.data.order_tools import lookup_order, calculate_cancellation_fee, calculate_service_credit_default
from src.data.ticket_tools import lookup_ticket, calculate_sla_status, list_tickets_for_account
from src.data.order_tools import list_orders_for_account
from src.retrieval.retriever import search_documents
from src.security.access_control import AccessDeniedError


def _safe_lookup_order(order_id, account_id):
    try:
        return lookup_order(order_id, account_id), None
    except AccessDeniedError as e:
        return None, str(e)


def _safe_lookup_ticket(ticket_id, account_id):
    try:
        return lookup_ticket(ticket_id, account_id), None
    except AccessDeniedError as e:
        return None, str(e)


def _docs(query, account_id, topic=None, top_k=4):
    try:
        return search_documents(query, account_id=account_id, topic=topic, top_k=top_k)
    except FileNotFoundError:
        return []


def build_account_summary(account_id: str) -> dict:
    return lookup_account(account_id)


def build_evidence(intent: str, entities: dict, message: str, account_id: str,
                    session_state: dict) -> dict:
    """Returns {"intent", "account_denied": [...], "structured": {...},
    "documents": [...], "notes": [...]} - the full verified evidence package."""
    account_denied = []
    structured = {}
    documents = []
    notes = []

    # Resolve order/ticket ids, falling back to conversation context on
    # pronoun-style follow-ups ("Section 21 - context-aware conversation").
    order_id = entities["order_ids"][0] if entities["order_ids"] else None
    ticket_id = entities["ticket_ids"][0] if entities["ticket_ids"] else None
    if not order_id and entities["has_followup_reference"] and session_state.get("last_order_id"):
        order_id = session_state["last_order_id"]
        notes.append(f"Interpreted follow-up reference as order {order_id} (from conversation context).")
    if not ticket_id and entities["has_followup_reference"] and session_state.get("last_ticket_id"):
        ticket_id = session_state["last_ticket_id"]

    # Always attempt to resolve any mentioned order/ticket first and verify
    # ownership, regardless of intent (Section 14 - verify ownership before
    # answering). Access-denied results are recorded, never silently dropped.
    if order_id:
        order, err = _safe_lookup_order(order_id, account_id)
        if err:
            account_denied.append(err)
        else:
            structured["order"] = order
    if ticket_id:
        ticket, err = _safe_lookup_ticket(ticket_id, account_id)
        if err:
            account_denied.append(err)
        else:
            structured["ticket"] = ticket

    if intent == "cancellation":
        if order_id and "order" in structured:
            structured["cancellation_calc"] = calculate_cancellation_fee(order_id, account_id)
            documents = _docs("cancellation fee waiver cancel order", account_id, topic="cancellation_and_credit")
        elif order_id and account_denied:
            pass  # access denied already recorded, nothing more to gather
        else:
            notes.append("No order ID was identified for this cancellation question.")
            documents = _docs(message, account_id, topic="cancellation_and_credit")

    elif intent == "service_credit":
        if order_id and "order" in structured:
            structured["credit_calc"] = calculate_service_credit_default(order_id, account_id)
            documents = _docs("failed pickup service credit", account_id, topic="cancellation_and_credit")
        else:
            notes.append("No order ID was identified for this service-credit question; "
                         "cannot compute eligibility without knowing which shipment.")
            documents = _docs(message, account_id, topic="cancellation_and_credit")

    elif intent == "sla":
        severity = entities["severity"] or (session_state.get("last_severity"))
        if severity:
            structured["sla_calc"] = calculate_sla_status(account_id, severity, ticket_id)
        else:
            notes.append("No severity (P1/P2/P3) was identified for this SLA question.")
        documents = _docs("support SLA response time target", account_id, topic="sla")

    elif intent == "order_status":
        if not order_id:
            notes.append("No order ID was identified.")
        documents = _docs("order status BOOKED PICKED_UP DELIVERED " + message, account_id,
                           topic="product_and_known_issues")

    elif intent == "list_orders":
        structured["orders"] = list_orders_for_account(account_id)

    elif intent == "ticket_status":
        if not ticket_id:
            notes.append("No ticket ID was identified.")

    elif intent == "list_tickets":
        structured["tickets"] = list_tickets_for_account(account_id)

    elif intent == "account_info":
        structured["account"] = lookup_account(account_id)

    else:  # general
        documents = _docs(message, account_id)
        # If an order/ticket was mentioned in an otherwise-general question,
        # also pull relevant product/known-issue docs (covers "why does my
        # SwiftShip shipment still show BOOKED" style questions).
        if order_id or ticket_id:
            documents += _docs(message, account_id, topic="product_and_known_issues")

    # Always attach a light account summary for context (plan name etc.),
    # cheap and helps the LLM phrase plan-specific answers correctly.
    structured["account_context"] = lookup_account(account_id)

    return {
        "intent": intent,
        "order_id": order_id,
        "ticket_id": ticket_id,
        "account_denied": account_denied,
        "structured": structured,
        "documents": documents,
        "notes": notes,
    }


def evidence_is_empty(evidence: dict) -> bool:
    """True when we found nothing usable at all: no structured facts beyond
    the generic account context, and no retrieved documents. Used to decide
    whether it's safe to skip the LLM call entirely and return the
    templated 'insufficient evidence' response."""
    structured_keys = set(evidence["structured"].keys()) - {"account_context"}
    return not structured_keys and not evidence["documents"] and not evidence["account_denied"]
