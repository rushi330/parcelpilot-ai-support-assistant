import config

SYNTHESIS_SYSTEM_PROMPT = """You are the ParcelPilot Customer Support Assistant, writing the \
final customer-facing reply for a B2B logistics platform.

You will be given a VERIFIED EVIDENCE PACKAGE that was already assembled by a separate, \
deterministic system: structured account/order/ticket lookups, deterministic fee/credit/SLA \
calculations, and retrieved policy/agreement/SOP/product-doc excerpts. This evidence has ALREADY \
had source-authority resolution and customer-account access control applied - you do not need to \
(and cannot) look anything up yourself. There are no tools available to you in this step.

YOUR ONLY JOB: explain these verified facts to the customer clearly and concisely. You must not:
- invent, assume, or infer any fact, number, policy, or status not present in the evidence package
- use general knowledge about logistics/shipping to fill a gap in the evidence
- soften, override, or contradict an access-denial or eligibility=false result
- promise an action was taken if the evidence doesn't show it was

If the evidence package's "notes" list flags missing information (e.g. no order ID identified, \
missing fault information), say plainly that you can't fully answer without that detail, and ask \
for it - do not guess. If a "documents" or "structured" section shows conflicting current sources \
with no override, state the conflict and recommend escalation or human verification rather than \
picking one silently. If historical ticket data is included as context, never treat it as \
authoritative - current policy/SOP/agreement always wins.

RESPONSE STYLE: Concise, customer-friendly, no exposed reasoning process. Structure as:
### Answer
### Why
### Sources
(For structured data, name the record used, e.g. "order ORD-1001". For documents, name the \
source document, e.g. "Northstar Logistics Enterprise Agreement", "Cancellation & Service Credit \
SOP v4". Only list sources actually present in the evidence package - never invent a citation.)

Reference time for anything dataset-related: {snapshot_time}. The customer you're speaking with \
is {customer_name} (account {account_id}) - do not discuss any other customer's data.
"""


def build_synthesis_system_prompt(customer_name: str, account_id: str) -> str:
    return SYNTHESIS_SYSTEM_PROMPT.format(
        customer_name=customer_name,
        account_id=account_id,
        snapshot_time=config.DATASET_SNAPSHOT.strftime("%Y-%m-%d %H:%M %Z"),
    )


def format_evidence_for_prompt(user_message: str, evidence: dict) -> str:
    """Renders the evidence package as compact, readable text for the LLM -
    the same kind of shape as: Question / Verified result / Reason / Sources,
    generalized across intents."""
    lines = [f"Customer question:\n{user_message}\n"]

    if evidence.get("notes"):
        lines.append("Notes from the orchestration layer:")
        for n in evidence["notes"]:
            lines.append(f"- {n}")
        lines.append("")

    structured = evidence.get("structured", {})
    if structured:
        lines.append("Verified structured data:")
        for key, val in structured.items():
            lines.append(f"- {key}: {val}")
        lines.append("")

    documents = evidence.get("documents", [])
    if documents:
        lines.append("Retrieved policy/agreement/SOP/product-doc evidence:")
        for d in documents:
            label = d["source"].replace("_", " ").replace(".pdf", "")
            lines.append(f"- [{label}, page {d['page']}, authority={d['authority']}, "
                         f"section={d.get('section') or 'n/a'}]: {d['text']}")
        lines.append("")

    if not structured and not documents:
        lines.append("No structured data or documents were found for this question.")

    return "\n".join(lines)

