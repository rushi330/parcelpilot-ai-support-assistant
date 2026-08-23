import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.retrieval.retriever import search_documents


def test_deprecated_policy_never_returned():
    results = search_documents("support policy severity response time", account_id="ACCT-003", top_k=10)
    for r in results:
        assert r["status"] != "deprecated", f"Deprecated doc leaked: {r['source']}"
    print("PASS: deprecated Support Policy v2 never appears in retrieval results")


def test_no_cross_account_agreement_leak():
    # LumenWorks (ACCT-002) must never see Northstar's (ACCT-001) agreement text
    results = search_documents("Northstar Priya Mehta CSM enterprise agreement", account_id="ACCT-002", top_k=10)
    for r in results:
        assert r["customer_account"] != "ACCT-001", "Cross-account agreement leaked!"
    print("PASS: no cross-account agreement leakage in retrieval")


def test_own_agreement_is_retrievable():
    results = search_documents("cancellation fee waiver", account_id="ACCT-001", top_k=10)
    sources = [r["source"] for r in results]
    assert "05_Northstar_Logistics_Enterprise_Agreement.pdf" in sources
    print("PASS: customer's own agreement retrievable for relevant queries")


def test_current_sop_retrievable():
    results = search_documents("service credit failed pickup", account_id="ACCT-003", top_k=5)
    assert any(r["source"].startswith("03_") for r in results)
    print("PASS: current Cancellation & Service Credit SOP retrievable")


if __name__ == "__main__":
    test_deprecated_policy_never_returned()
    test_no_cross_account_agreement_leak()
    test_own_agreement_is_retrievable()
    test_current_sop_retrievable()
    print("\nALL RETRIEVAL TESTS PASSED")
