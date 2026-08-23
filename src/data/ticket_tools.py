"""Account-scoped ticket lookups and deterministic SLA status calculation.

ASSUMPTION (documented, since the source policies define "business hours"/
"business days" without giving exact operating hours): business hours are
Mon-Fri 09:00-18:00 Asia/Kolkata (9 hours/day), and "1 business day" is
treated as 9 business hours for elapsed-time comparison. 24x7 targets use
pure calendar elapsed time. This is the smallest reasonable assumption
needed to make SLA breach checks concrete; it is applied consistently.
"""
import datetime as dt
import pandas as pd
import config
from src.data.workbook_loader import get_tickets_df
from src.data.account_tools import lookup_account
from src.security.access_control import enforce_account_match, require_account_id

BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 18

# Default SLA targets (hours), from Support Policy v3, keyed by plan.
# Each value is (target_hours, is_24x7, unit_label)
DEFAULT_SLA_HOURS = {
    "Enterprise": {"P1": (0.5, True), "P2": (2, False), "P3": (9, False)},   # P3 = 1 business day = 9h
    "Growth":     {"P1": (2, False),  "P2": (4, False), "P3": (18, False)},  # P3 = 2 business days
    "Standard":   {"P1": (4, False),  "P2": (9, False), "P3": (18, False)},
}

# Northstar (ACCT-001) contract-specific SLA overrides (hours)
NORTHSTAR_SLA_HOURS = {"P1": (0.25, True), "P2": (1, True), "P3": (8, False)}


def _row_to_ticket_dict(r: pd.Series) -> dict:
    def fmt(ts):
        if pd.isna(ts):
            return None
        return ts.isoformat()
    return {
        "ticket_id": r["ticket_id"],
        "account_id": r["account_id"],
        "created_at": fmt(r["created_at"]),
        "status": r["status"],
        "subject": r["subject"],
        "description": r["description"],
        "channel": r["channel"],
        "last_customer_message_at": fmt(r["last_customer_message_at"]),
        "historical_resolution": None if pd.isna(r["historical_resolution"]) else r["historical_resolution"],
    }


def lookup_ticket(ticket_id: str, account_id: str) -> dict:
    require_account_id(account_id)
    df = get_tickets_df()
    row = df[df["ticket_id"] == ticket_id]
    if row.empty:
        return {"found": False, "error": f"No ticket found with id {ticket_id}"}
    r = row.iloc[0]
    enforce_account_match(r["account_id"], account_id, resource=f"ticket {ticket_id}")
    return {"found": True, **_row_to_ticket_dict(r)}


def list_tickets_for_account(account_id: str) -> dict:
    require_account_id(account_id)
    df = get_tickets_df()
    rows = df[df["account_id"] == account_id]
    return {"found": True, "tickets": [_row_to_ticket_dict(r) for _, r in rows.iterrows()]}


def _elapsed_business_hours(start: dt.datetime, end: dt.datetime) -> float:
    """Elapsed business hours (Mon-Fri 09:00-18:00) between two tz-aware datetimes."""
    if end <= start:
        return 0.0
    total = 0.0
    cursor = start
    while cursor < end:
        day_end = cursor.replace(hour=BUSINESS_END_HOUR, minute=0, second=0, microsecond=0)
        day_start = cursor.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
        if cursor < day_start:
            cursor = day_start
            continue
        if cursor.weekday() >= 5 or cursor >= day_end:
            # move to next day's business start
            nxt = (cursor + dt.timedelta(days=1)).replace(
                hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
            cursor = nxt
            continue
        segment_end = min(end, day_end)
        total += (segment_end - cursor).total_seconds() / 3600.0
        cursor = segment_end
        if cursor >= day_end:
            nxt = (cursor + dt.timedelta(days=1)).replace(
                hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
            cursor = nxt
    return total


def calculate_sla_status(account_id: str, severity: str, ticket_id: str = None) -> dict:
    """Determine the applicable first-response SLA target for this account/severity
    and whether it is currently breached, using the dataset snapshot as 'now'.
    Applies Northstar's contract override when account_id == ACCT-001; otherwise
    uses the current default Support Policy v3 target for the account's plan.
    """
    require_account_id(account_id)
    severity = severity.upper().strip()
    if severity not in ("P1", "P2", "P3"):
        return {"error": f"Unknown severity '{severity}'. Expected P1, P2, or P3."}

    account = lookup_account(account_id)
    if not account.get("found"):
        return account

    if account_id == "ACCT-001":
        target_hours, is_24x7 = NORTHSTAR_SLA_HOURS[severity]
        source = "Northstar Logistics Enterprise Agreement (contract override)"
    else:
        plan = account["plan"]
        if plan not in DEFAULT_SLA_HOURS:
            return {"error": f"No default SLA table for plan '{plan}'.", "uncertain": True}
        target_hours, is_24x7 = DEFAULT_SLA_HOURS[plan][severity]
        source = f"Support Policy v3 (current), {plan} plan default"

    result = {
        "account_id": account_id, "severity": severity,
        "target_hours": target_hours, "is_24x7": is_24x7, "source": source,
    }

    if ticket_id:
        ticket = lookup_ticket(ticket_id, account_id)
        if not ticket.get("found"):
            result["ticket_lookup_error"] = ticket.get("error")
            return result
        created_at = pd.Timestamp(ticket["created_at"])
        now = config.DATASET_SNAPSHOT
        if is_24x7:
            elapsed = (now - created_at).total_seconds() / 3600.0
        else:
            elapsed = _elapsed_business_hours(created_at, now)
        breached = elapsed > target_hours
        result.update({
            "ticket_id": ticket_id,
            "created_at": ticket["created_at"],
            "elapsed_hours": round(elapsed, 2),
            "breached": breached,
        })
    return result
