"""Account-scoped order lookups and deterministic service-credit calculation.

IMPORTANT: numeric business-rule calculations (cancellation fee eligibility,
service credit amounts) are done here in plain Python, not by the LLM, so
they are reliable and auditable.
"""
import math
import pandas as pd
import config
from src.data.workbook_loader import get_orders_df
from src.security.access_control import enforce_account_match, require_account_id


def _row_to_order_dict(r: pd.Series) -> dict:
    def fmt(ts):
        if pd.isna(ts):
            return None
        return ts.isoformat()

    return {
        "order_id": r["order_id"],
        "account_id": r["account_id"],
        "carrier": r["carrier"],
        "status": r["status"],
        "booked_at": fmt(r["booked_at"]),
        "pickup_window_start": fmt(r["pickup_window_start"]),
        "pickup_window_end": fmt(r["pickup_window_end"]),
        "pickup_actual_at": fmt(r["pickup_actual_at"]),
        "shipment_fee_inr": None if pd.isna(r["shipment_fee_inr"]) else int(r["shipment_fee_inr"]),
        "carrier_fault": None if pd.isna(r["carrier_fault"]) else bool(r["carrier_fault"]),
        "customer_fault": None if pd.isna(r["customer_fault"]) else bool(r["customer_fault"]),
        "cancellation_requested_at": fmt(r["cancellation_requested_at"]),
        "notes": None if pd.isna(r["notes"]) else r["notes"],
    }


def lookup_order(order_id: str, account_id: str) -> dict:
    """Look up an order. Enforces that the order belongs to account_id."""
    require_account_id(account_id)
    df = get_orders_df()
    row = df[df["order_id"] == order_id]
    if row.empty:
        return {"found": False, "error": f"No order found with id {order_id}"}
    r = row.iloc[0]
    enforce_account_match(r["account_id"], account_id, resource=f"order {order_id}")
    return {"found": True, **_row_to_order_dict(r)}


def list_orders_for_account(account_id: str) -> dict:
    """List all orders belonging to the authenticated account only."""
    require_account_id(account_id)
    df = get_orders_df()
    rows = df[df["account_id"] == account_id]
    return {"found": True, "orders": [_row_to_order_dict(r) for _, r in rows.iterrows()]}


def calculate_cancellation_fee(order_id: str, account_id: str) -> dict:
    """Determine the DEFAULT cancellation eligibility/fee per SOP v4, purely
    from order status/timestamps. This is the fallback the agent applies
    unless a customer agreement overrides it (override logic lives in the
    agent layer, which compares this result against agreement text)."""
    order = lookup_order(order_id, account_id)
    if not order.get("found"):
        return order

    status = order["status"]
    now = config.DATASET_SNAPSHOT

    if status == "DELIVERED":
        return {"order_id": order_id, "cancellable": False, "fee_inr": None,
                "rule": "DELIVERED orders cannot be cancelled (default SOP)."}
    if status == "PICKED_UP":
        return {"order_id": order_id, "cancellable": False, "fee_inr": None,
                "rule": "PICKED_UP orders cannot be cancelled; return-to-origin workflow applies (default SOP)."}
    if status == "BOOKED":
        booked_at = pd.Timestamp(order["booked_at"]) if order["booked_at"] else None
        if booked_at is None:
            return {"order_id": order_id, "cancellable": True, "fee_inr": None,
                     "rule": "BOOKED order, but booking time unknown; cannot determine fee window.",
                     "uncertain": True}
        # Use the actual cancellation-request time if the customer has already
        # requested one; otherwise evaluate "if cancelled now" using the dataset
        # snapshot time as a hypothetical reference point.
        cancel_req_at = pd.Timestamp(order["cancellation_requested_at"]) if order["cancellation_requested_at"] else None
        reference_time = cancel_req_at if cancel_req_at is not None else now
        basis = "at the time cancellation was requested" if cancel_req_at is not None else "if cancelled now"
        minutes_since_booking = (reference_time - booked_at).total_seconds() / 60.0
        if minutes_since_booking <= 30:
            return {"order_id": order_id, "cancellable": True, "fee_inr": 0,
                     "rule": f"BOOKED, {basis} ({minutes_since_booking:.0f} min after booking, "
                             f"within 30 min) -> no fee (default SOP)."}
        else:
            return {"order_id": order_id, "cancellable": True, "fee_inr": 250,
                     "rule": f"BOOKED, {basis} ({minutes_since_booking:.0f} min after booking, >30 min) -> "
                             f"INR 250 default cancellation fee applies unless a customer agreement "
                             f"explicitly waives it (default SOP)."}
    return {"order_id": order_id, "cancellable": False, "fee_inr": None,
             "rule": f"Unrecognized order status '{status}'.", "uncertain": True}


def calculate_service_credit_default(order_id: str, account_id: str) -> dict:
    """Compute the DEFAULT failed-pickup service credit per SOP v4:
    eligible when pickup is >2 hours past scheduled pickup-window end,
    carrier is at fault, and customer is not at fault. Credit = lower of
    INR 500 or 10% of shipment fee. Agreement overrides are applied in the
    agent layer (Northstar defers to this default; LumenWorks overrides it).
    """
    order = lookup_order(order_id, account_id)
    if not order.get("found"):
        return order

    if order["carrier_fault"] is None or order["customer_fault"] is None:
        return {"order_id": order_id, "eligible": None,
                "reason": "Carrier-fault / customer-fault information is missing; cannot determine eligibility.",
                "uncertain": True}

    if order["customer_fault"]:
        return {"order_id": order_id, "eligible": False,
                "reason": "Customer is at fault; not eligible for a failed-pickup service credit (default SOP)."}

    if not order["carrier_fault"]:
        return {"order_id": order_id, "eligible": False,
                "reason": "Carrier is not marked at fault; not eligible under the default SOP."}

    window_end = pd.Timestamp(order["pickup_window_end"]) if order["pickup_window_end"] else None
    if window_end is None:
        return {"order_id": order_id, "eligible": None,
                "reason": "Pickup window end is unknown; cannot determine lateness.",
                "uncertain": True}

    pickup_actual = pd.Timestamp(order["pickup_actual_at"]) if order["pickup_actual_at"] else None
    reference_time = pickup_actual if pickup_actual is not None else config.DATASET_SNAPSHOT
    hours_late = (reference_time - window_end).total_seconds() / 3600.0

    if hours_late <= 2:
        return {"order_id": order_id, "eligible": False, "hours_late": round(hours_late, 2),
                "reason": f"Pickup is only {hours_late:.2f}h past the window end; default threshold is >2h."}

    fee = order["shipment_fee_inr"] or 0
    credit = min(500, math.floor(fee * 0.10))
    return {
        "order_id": order_id, "eligible": True, "hours_late": round(hours_late, 2),
        "credit_inr": credit,
        "requires_manager_approval": credit > 1000,
        "reason": f"Pickup is {hours_late:.2f}h past the scheduled window end (>2h), carrier at fault, "
                   f"customer not at fault -> default SOP credit = lower of INR 500 / 10% of fee "
                   f"(fee INR {fee}) = INR {credit}.",
    }
