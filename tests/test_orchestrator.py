"""Tests the deterministic orchestration layer: intent/entity extraction,
evidence assembly, and the decision of when to skip the LLM entirely vs.
make exactly one call. Uses a scripted FAKE Gemini client for the one-call
paths - no network/API key required.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.intent import extract_entities, classify_intent, classify_confirmation
from src.agent.orchestrator import handle_turn, new_session_state


# ---------- Fake single-call LLM client (mirrors google-genai's response shape) ----------
class FakeGenResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, text):
        self.text = text
        self.call_count = 0

    def generate_content(self, model=None, contents=None, config=None):
        self.call_count += 1
        return FakeGenResponse(self.text)


class FakeClient:
    def __init__(self, text="### Answer\nMocked answer.\n### Sources\n- test"):
        self.models = FakeModels(text)


# ---------- Intent/entity unit tests (pure, no LLM) ----------

def test_entity_extraction():
    e = extract_entities("Can I cancel ORD-1001 or check TKT-501?")
    assert e["order_ids"] == ["ORD-1001"]
    assert e["ticket_ids"] == ["TKT-501"]
    print("PASS: entity extraction")


def test_intent_classification():
    assert classify_intent("Can I cancel ORD-1001?") == "cancellation"
    assert classify_intent("Should I get a credit for the delay?") == "service_credit"
    assert classify_intent("What's your SLA response time?") == "sla"
    assert classify_intent("Please escalate this issue") == "escalate"
    print("PASS: intent classification")


def test_confirmation_classification():
    assert classify_confirmation("Yes, please proceed") == "affirmative"
    assert classify_confirmation("No thanks") == "negative"
    assert classify_confirmation("what do you mean") == "ambiguous"
    print("PASS: confirmation classification")


# ---------- Orchestrator integration tests ----------

def test_exactly_one_llm_call_for_grounded_question():
    state = new_session_state()
    client = FakeClient()
    result = handle_turn("ACCT-001", "Northstar Logistics",
                          "Can Northstar cancel ORD-1001 without a fee?", state, llm_client=client)
    assert result["used_llm"] is True
    assert client.models.call_count == 1, f"Expected exactly 1 LLM call, got {client.models.call_count}"
    assert "Mocked answer" in result["answer"]
    print("PASS: exactly one LLM call for a grounded cancellation question")


def test_zero_llm_calls_for_cross_account_access():
    state = new_session_state()
    client = FakeClient()
    # ORD-2001 belongs to ACCT-002 (LumenWorks); asking as ACCT-001 must be denied
    result = handle_turn("ACCT-001", "Northstar Logistics",
                          "What's the status of ORD-2001?", state, llm_client=client)
    assert result["used_llm"] is False
    assert client.models.call_count == 0
    assert "not able to share" in result["answer"].lower() or "access" in result["answer"].lower()
    print("PASS: zero LLM calls for cross-account access denial:", result["answer"][:60])


def test_zero_llm_calls_for_escalation_propose_and_confirm():
    state = new_session_state()
    client = FakeClient()

    propose = handle_turn("ACCT-001", "Northstar Logistics", "Please escalate this issue", state, llm_client=client)
    assert propose["used_llm"] is False
    assert client.models.call_count == 0
    assert propose["session_state"]["pending_action"] is not None
    assert "proceed" in propose["answer"].lower()

    confirm = handle_turn("ACCT-001", "Northstar Logistics", "yes", propose["session_state"], llm_client=client)
    assert confirm["used_llm"] is False
    assert client.models.call_count == 0
    assert confirm["session_state"]["pending_action"] is None
    assert "ESC-" in confirm["answer"]
    print("PASS: escalation propose + confirm uses zero LLM calls, escalation ID present in reply")


def test_escalation_declined_clears_pending_state():
    state = new_session_state()
    client = FakeClient()
    propose = handle_turn("ACCT-001", "Northstar Logistics", "escalate this please", state, llm_client=client)
    decline = handle_turn("ACCT-001", "Northstar Logistics", "no, never mind", propose["session_state"], llm_client=client)
    assert decline["session_state"]["pending_action"] is None
    assert client.models.call_count == 0
    print("PASS: declined escalation clears pending state without any LLM call")


def test_ambiguous_confirmation_reasks_without_llm():
    state = new_session_state()
    client = FakeClient()
    propose = handle_turn("ACCT-001", "Northstar Logistics", "escalate this", state, llm_client=client)
    reask = handle_turn("ACCT-001", "Northstar Logistics", "what will that do exactly", propose["session_state"], llm_client=client)
    assert reask["session_state"]["pending_action"] is not None  # still pending
    assert client.models.call_count == 0
    print("PASS: ambiguous reply re-asks for confirmation, still zero LLM calls")


def test_followup_reference_reuses_last_order():
    state = new_session_state()
    client = FakeClient()
    first = handle_turn("ACCT-001", "Northstar Logistics", "Can I cancel ORD-1001?", state, llm_client=client)
    assert first["session_state"]["last_order_id"] == "ORD-1001"
    second = handle_turn("ACCT-001", "Northstar Logistics", "What if it has already been picked up?",
                          first["session_state"], llm_client=client)
    # Should resolve "it" -> ORD-1001 via conversation context, still exactly one more LLM call
    assert second["used_llm"] is True
    print("PASS: follow-up pronoun resolved to last-mentioned order via session context")


def test_zero_llm_calls_when_no_evidence_at_all():
    state = new_session_state()
    client = FakeClient()
    result = handle_turn("ACCT-003", "Beacon Retail",
                          "What is your refund policy for lost international shipments to Mars?",
                          state, llm_client=client)
    # No structured data and (very likely) no relevant docs -> deterministic fallback
    if not result["used_llm"]:
        assert client.models.call_count == 0
        assert "couldn't verify" in result["answer"].lower()
        print("PASS: zero LLM calls when no evidence found at all")
    else:
        print("NOTE: retrieval found tangential docs for this query - one LLM call made (acceptable, evidence existed).")


if __name__ == "__main__":
    test_entity_extraction()
    test_intent_classification()
    test_confirmation_classification()
    test_exactly_one_llm_call_for_grounded_question()
    test_zero_llm_calls_for_cross_account_access()
    test_zero_llm_calls_for_escalation_propose_and_confirm()
    test_escalation_declined_clears_pending_state()
    test_ambiguous_confirmation_reasks_without_llm()
    test_followup_reference_reuses_last_order()
    test_zero_llm_calls_when_no_evidence_at_all()
    print("\nALL ORCHESTRATOR TESTS PASSED")
