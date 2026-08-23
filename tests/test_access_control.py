import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.account_tools import lookup_account
from src.data.order_tools import lookup_order
from src.data.ticket_tools import lookup_ticket
from src.security.access_control import AccessDeniedError


def test_valid_account_lookup():
    r = lookup_account("ACCT-001")
    assert r["found"] and r["account_id"] == "ACCT-001"
    print("PASS: valid account lookup")


def test_valid_order_lookup():
    r = lookup_order("ORD-1001", "ACCT-001")
    assert r["found"] and r["account_id"] == "ACCT-001"
    print("PASS: valid order lookup (own account)")


def test_invalid_cross_account_order_lookup():
    try:
        lookup_order("ORD-1001", "ACCT-002")  # ORD-1001 belongs to ACCT-001
        assert False, "should have raised AccessDeniedError"
    except AccessDeniedError:
        print("PASS: cross-account order lookup denied")


def test_invalid_cross_account_ticket_lookup():
    try:
        lookup_ticket("TKT-501", "ACCT-002")  # TKT-501 belongs to ACCT-001
        assert False, "should have raised AccessDeniedError"
    except AccessDeniedError:
        print("PASS: cross-account ticket lookup denied")


def test_unknown_order_id_fails_safely():
    r = lookup_order("ORD-9999", "ACCT-001")
    assert r["found"] is False
    print("PASS: unknown order id handled without crash")


if __name__ == "__main__":
    test_valid_account_lookup()
    test_valid_order_lookup()
    test_invalid_cross_account_order_lookup()
    test_invalid_cross_account_ticket_lookup()
    test_unknown_order_id_fails_safely()
    print("\nALL ACCESS CONTROL TESTS PASSED")
