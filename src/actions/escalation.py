"""Mocked state-changing action: create_escalation.

This is a LOCAL MOCK STORE for the assessment - no real ticketing system is
called. Escalations only get written here after the caller has already
obtained explicit user confirmation (enforced in the agent layer, not here -
but this module never auto-executes on its own; it always requires a
create_escalation() call with confirmed=True).
"""
import itertools
import datetime as dt
import config

_escalations = {}
_id_counter = itertools.count(1)


def create_escalation(account_id: str, reason: str, priority: str,
                       related_ticket_id: str = None, confirmed: bool = False) -> dict:
    """Create a mock escalation. Will refuse to execute unless confirmed=True,
    as a last-line safeguard in addition to the agent-level confirmation gate.
    """
    if not confirmed:
        return {
            "executed": False,
            "error": "Action not confirmed. An escalation was NOT created. "
                     "Explicit user confirmation is required before this action executes.",
        }

    esc_id = f"ESC-{next(_id_counter):04d}"
    record = {
        "escalation_id": esc_id,
        "account_id": account_id,
        "reason": reason,
        "priority": priority,
        "related_ticket_id": related_ticket_id,
        "status": "Created",
        "created_at": config.DATASET_SNAPSHOT.isoformat(),
    }
    _escalations[esc_id] = record
    return {"executed": True, **record}


def list_escalations_for_account(account_id: str) -> list[dict]:
    return [e for e in _escalations.values() if e["account_id"] == account_id]
