"""Deterministic orchestration layer.

    User
      |
      v
    Deterministic orchestration (this module)
      |
      v
    Intent + entity extraction (src/agent/intent.py) - no LLM
      |
      v
    Evidence assembly (src/agent/evidence.py):
        - account scope / security (src/security/access_control.py)
        - structured lookups + calculations (src/data/*)
        - semantic retrieval + authority filtering (src/retrieval/*)
      |
      v
    Verified evidence package
      |
      v
    Decision: is this a fully-deterministic outcome (escalation flow,
    access denial, empty evidence)? -> templated response, ZERO LLM calls
    Otherwise -> exactly ONE LLM call (src/agent/llm_client.py) to explain
    the verified evidence in natural language.
      |
      v
    Response (+ steps performed + sources, for UI display)

`session_state` is a small plain dict the caller (Streamlit) persists across
turns - it holds conversation context (last order/ticket/severity mentioned,
and any pending unconfirmed action) so follow-ups and confirmations work
without needing multi-turn LLM chat state at all.
"""
from src.agent.intent import extract_entities, classify_intent, classify_confirmation
from src.agent.evidence import build_evidence, evidence_is_empty
from src.agent.llm_client import synthesize_response
from src.agent.templates import (
    access_denied_response, insufficient_evidence_response,
    escalation_proposed_response, escalation_executed_response,
    escalation_declined_response, escalation_reask_response,
)
from src.actions.escalation import create_escalation


def new_session_state() -> dict:
    return {
        "last_order_id": None,
        "last_ticket_id": None,
        "last_severity": None,
        "last_topic_reason": None,
        "pending_action": None,
    }


def _steps_from_evidence(evidence: dict) -> list[str]:
    steps = []
    if evidence.get("order_id"):
        steps.append(f"Verified order {evidence['order_id']} ownership and looked up its details.")
    if evidence.get("ticket_id"):
        steps.append(f"Verified ticket {evidence['ticket_id']} ownership and looked up its details.")
    structured = evidence.get("structured", {})
    if "cancellation_calc" in structured:
        steps.append("Calculated default cancellation eligibility/fee from order data and current SOP.")
    if "credit_calc" in structured:
        steps.append("Calculated default failed-pickup service-credit eligibility/amount.")
    if "sla_calc" in structured:
        steps.append("Calculated applicable SLA target and breach status.")
    if evidence.get("documents"):
        steps.append(f"Searched policies/agreements/SOPs/product docs ({len(evidence['documents'])} relevant excerpt(s) found).")
    if evidence.get("notes"):
        steps.extend(evidence["notes"])
    if not steps:
        steps.append("Checked your account context.")
    return steps


def handle_turn(account_id: str, customer_name: str, user_message: str,
                 session_state: dict, llm_client=None) -> dict:
    """Process one customer message. Returns:
    {"answer": str, "used_llm": bool, "sources": [...], "steps": [...], "session_state": dict}
    """
    session_state = dict(session_state)  # don't mutate caller's dict in place

    # --- 1. Pending confirmation takes priority over everything else ---
    pending = session_state.get("pending_action")
    if pending:
        outcome = classify_confirmation(user_message)
        if outcome == "affirmative":
            result = create_escalation(
                account_id=account_id, reason=pending["reason"], priority=pending["priority"],
                related_ticket_id=pending.get("related_ticket_id"), confirmed=True,
            )
            session_state["pending_action"] = None
            resp = escalation_executed_response(result)
        elif outcome == "negative":
            session_state["pending_action"] = None
            resp = escalation_declined_response()
        else:
            resp = escalation_reask_response(pending["reason"], pending["priority"])
        return {**resp, "session_state": session_state}

    # --- 2. Entity extraction + intent classification (zero LLM calls) ---
    entities = extract_entities(user_message)
    intent = classify_intent(user_message)

    # --- 3. Escalation requests are prepared deterministically and always
    #        wait for a separate confirmation turn (handled in step 1 above
    #        on the NEXT message). No LLM call needed to phrase this. ---
    if intent == "escalate":
        reason = session_state.get("last_topic_reason") or user_message.strip()
        priority = entities["severity"] or session_state.get("last_severity") or "P2"
        related_ticket_id = (entities["ticket_ids"][0] if entities["ticket_ids"]
                              else session_state.get("last_ticket_id"))
        session_state["pending_action"] = {
            "reason": reason, "priority": priority, "related_ticket_id": related_ticket_id,
        }
        resp = escalation_proposed_response(reason, priority, related_ticket_id)
        return {**resp, "session_state": session_state}

    # --- 4. Everything else: assemble verified evidence deterministically ---
    evidence = build_evidence(intent, entities, user_message, account_id, session_state)

    # Update conversation context for future follow-ups/escalations.
    if evidence.get("order_id"):
        session_state["last_order_id"] = evidence["order_id"]
    if evidence.get("ticket_id"):
        session_state["last_ticket_id"] = evidence["ticket_id"]
    if entities.get("severity"):
        session_state["last_severity"] = entities["severity"]
    topic_ref = evidence.get("order_id") or evidence.get("ticket_id") or "your account"
    session_state["last_topic_reason"] = f"Customer question ({intent}) regarding {topic_ref}: {user_message.strip()}"

    # --- 5. Cross-account access denial: deterministic refusal, no LLM call ---
    if evidence["account_denied"]:
        resp = access_denied_response(evidence["account_denied"])
        return {**resp, "session_state": session_state}

    # --- 6. No usable evidence at all: deterministic "can't verify", no LLM call ---
    if evidence_is_empty(evidence):
        resp = insufficient_evidence_response()
        return {**resp, "session_state": session_state}

    # --- 7. The ONE LLM call: explain the verified evidence package ---
    answer = synthesize_response(customer_name, account_id, user_message, evidence, client=llm_client)
    sources = [
        {"source": d["source"], "page": d["page"], "section": d.get("section"), "authority": d["authority"]}
        for d in evidence["documents"]
    ]
    steps = _steps_from_evidence(evidence)

    return {
        "answer": answer or "I wasn't able to generate a response. Please try rephrasing.",
        "used_llm": True,
        "sources": sources,
        "steps": steps,
        "session_state": session_state,
    }
