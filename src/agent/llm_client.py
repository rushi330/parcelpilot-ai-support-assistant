"""Exactly ONE LLM call per turn: plain text generation, no function calling,
no tool loop. The model receives only the pre-verified evidence package and
is asked to explain it in natural language. Everything upstream of this
(retrieval, lookups, calculations, access control, escalation state) is
already done by the time this is called.
"""
import config
from src.agent.prompts import build_synthesis_system_prompt, format_evidence_for_prompt


def _get_client():
    from google import genai
    if not config.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Set it via environment variable or "
            "Streamlit secrets before starting a chat."
        )
    return genai.Client(api_key=config.GEMINI_API_KEY)


def synthesize_response(customer_name: str, account_id: str, user_message: str,
                         evidence: dict, client=None) -> str:
    """The single LLM call. `client`, when provided, must expose
    `.models.generate_content(model=..., contents=..., config=...)` returning
    an object with `.text` - this is injectable so orchestration logic can be
    tested without a real API key (see tests/test_orchestrator.py)."""
    from google.genai import types

    system_prompt = build_synthesis_system_prompt(customer_name, account_id)
    evidence_text = format_evidence_for_prompt(user_message, evidence)

    active_client = client or _get_client()
    response = active_client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=evidence_text,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return response.text or ""
