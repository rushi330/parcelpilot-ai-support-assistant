"""Fully-deterministic response templates. These paths never call the LLM at
all, since the content is already precise, structured, and doesn't benefit
from - or shouldn't be subject to - free-form generation:

  - Cross-account access denial (safety-critical: never let generation soften/leak)
  - Escalation propose / confirm / decline / re-ask (already-structured data)
  - "No evidence found at all" fallback (avoids ever giving the LLM a chance
    to fill an empty package with invented content)

Every other case goes through exactly one LLM call (src/agent/llm_client.py)
with a verified evidence package.
"""
import config


def access_denied_response(account_denied: list[str]) -> dict:
    reason = account_denied[0] if account_denied else "That record does not belong to your account."
    return {
        "answer": (
            "I'm not able to share that - it doesn't belong to your account, and I can only "
            "access information for your own ParcelPilot account. If you believe this is an "
            "error, please contact ParcelPilot support directly."
        ),
        "used_llm": False,
        "sources": [],
        "steps": ["Verified record ownership against your authenticated account.", "Access denied - record belongs to a different account."],
    }


def insufficient_evidence_response() -> dict:
    return {
        "answer": (
            "I couldn't verify that from the available ParcelPilot information. The available "
            "records and documentation don't establish a reliable answer to this question. I'd "
            "recommend escalating this to ParcelPilot support, or let me know if you can share "
            "more detail (e.g. an order or ticket ID) and I'll take another look."
        ),
        "used_llm": False,
        "sources": [],
        "steps": ["Searched policies, agreements, and your account records.", "No matching evidence found."],
    }


def escalation_proposed_response(reason: str, priority: str, related_ticket_id: str = None) -> dict:
    lines = [
        "I can escalate this for you. Here's what I'd submit:",
        "",
        f"**Proposed action:** Create escalation",
        f"**Priority:** {priority}",
        f"**Reason:** {reason}",
    ]
    if related_ticket_id:
        lines.append(f"**Related ticket:** {related_ticket_id}")
    lines.append("")
    lines.append("Do you want me to proceed? (reply **yes** to confirm, or **no** to cancel)")
    return {
        "answer": "\n".join(lines),
        "used_llm": False,
        "sources": [],
        "steps": ["Prepared escalation proposal.", "Awaiting your explicit confirmation before creating it."],
    }


def escalation_executed_response(result: dict) -> dict:
    return {
        "answer": (
            f"Done - escalation created.\n\n"
            f"**Escalation ID:** {result['escalation_id']}\n"
            f"**Status:** {result['status']}\n"
            f"**Priority:** {result['priority']}\n\n"
            f"A member of the ParcelPilot support team will follow up."
        ),
        "used_llm": False,
        "sources": [],
        "steps": ["Received your confirmation.", "Escalation created."],
    }


def escalation_declined_response() -> dict:
    return {
        "answer": "No problem - I haven't created an escalation. Let me know if you'd like anything else.",
        "used_llm": False,
        "sources": [],
        "steps": ["You declined the proposed escalation - no action taken."],
    }


def escalation_reask_response(reason: str, priority: str) -> dict:
    return {
        "answer": (
            f"Just to confirm before I proceed: I'd be creating a **{priority}** escalation for "
            f"\"{reason}\". Reply **yes** to confirm or **no** to cancel."
        ),
        "used_llm": False,
        "sources": [],
        "steps": ["Waiting for a clear yes/no to the pending escalation."],
    }
