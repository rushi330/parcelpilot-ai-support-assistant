import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.order_tools import calculate_cancellation_fee, calculate_service_credit_default
from src.data.ticket_tools import calculate_sla_status


def test_cancellation_within_30_min_no_fee():
    # ORD-3001 (Beacon): booked 10:25, cancellation requested 10:40 -> 15 min -> no fee
    r = calculate_cancellation_fee("ORD-3001", "ACCT-003")
    assert r["fee_inr"] == 0
    print("PASS:", r["rule"])


def test_cancellation_after_30_min_default_fee():
    # ORD-1001 (Northstar): booked 09:00, cancel requested 11:00 -> 120 min -> default fee 250
    # (agreement override is applied at the AGENT layer, not here - this tests the raw default)
    r = calculate_cancellation_fee("ORD-1001", "ACCT-001")
    assert r["fee_inr"] == 250
    print("PASS:", r["rule"])


def test_picked_up_order_not_cancellable():
    r = calculate_cancellation_fee("ORD-1002", "ACCT-001")
    assert r["cancellable"] is False
    print("PASS:", r["rule"])


def test_service_credit_eligible_default():
    # ORD-2002 (LumenWorks): carrier fault, no customer fault, >2h late -> default eligible
    r = calculate_service_credit_default("ORD-2002", "ACCT-002")
    assert r["eligible"] is True
    assert r["credit_inr"] == 240  # min(500, 10% of 2400)
    print("PASS:", r["reason"])


def test_service_credit_not_eligible_no_carrier_fault():
    # ORD-1001: carrier_fault=False -> not eligible
    r = calculate_service_credit_default("ORD-1001", "ACCT-001")
    assert r["eligible"] is False
    print("PASS:", r["reason"])


def test_sla_northstar_p1_override():
    r = calculate_sla_status("ACCT-001", "P1")
    assert r["target_hours"] == 0.25
    assert "Northstar" in r["source"]
    print("PASS: Northstar P1 override =", r["target_hours"], "hours 24x7 =", r["is_24x7"])


def test_sla_default_enterprise_p1():
    # ACCT-004 Axis Labs, Enterprise, no custom contract -> default v3 policy
    r = calculate_sla_status("ACCT-004", "P1")
    assert r["target_hours"] == 0.5
    assert "Support Policy v3" in r["source"]
    print("PASS: default Enterprise P1 =", r["target_hours"], "hours")


def test_sla_breach_detection():
    # TKT-501 (Northstar P1 outage), created 10:30, snapshot 11:00 -> 30 min elapsed
    # Northstar P1 target = 15 min 24x7 -> breached
    r = calculate_sla_status("ACCT-001", "P1", "TKT-501")
    assert r["breached"] is True
    print("PASS: SLA breach correctly detected -", r["elapsed_hours"], "h elapsed vs", r["target_hours"], "h target")


if __name__ == "__main__":
    test_cancellation_within_30_min_no_fee()
    test_cancellation_after_30_min_default_fee()
    test_picked_up_order_not_cancellable()
    test_service_credit_eligible_default()
    test_service_credit_not_eligible_no_carrier_fault()
    test_sla_northstar_p1_override()
    test_sla_default_enterprise_p1()
    test_sla_breach_detection()
    print("\nALL BUSINESS RULE TESTS PASSED")
