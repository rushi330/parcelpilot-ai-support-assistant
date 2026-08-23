# ParcelPilot Customer Support Assistant

A customer-facing AI support chatbot for ParcelPilot, a B2B logistics platform. Customers ask
natural-language questions about their account, orders, tickets, cancellations, service credits,
and support SLAs; the assistant answers using retrieval over current policies/agreements plus
deterministic lookups over structured account data — never by inventing facts.

## Problem statement

The source material is intentionally imperfect: one support policy is deprecated but still present,
customer-specific agreements override generic defaults on some (not all) topics, two historical
tickets contain guidance that is now known to be wrong, and a couple of "known issues" only apply
to specific symptoms. A support bot that treats every document as equally authoritative, or that
answers structured account questions by embedding a spreadsheet into a vector store, will
confidently give wrong answers or leak one customer's data to another. This project is built
specifically to avoid that.

## Architecture

**Cost-optimized design: at most one LLM call per customer turn** (often zero — see below).
Everything upstream of the LLM is deterministic Python: intent detection, entity extraction,
account-scoped structured lookups, semantic retrieval, and authority resolution all happen first
and produce a **verified evidence package**. The LLM's only job is to explain that package in
natural language — it never calls tools, never runs a multi-round agent loop, and never sees
anything outside its own account's evidence.

```
                    CUSTOMER
                       |
                       v
                STREAMLIT CHAT  (app.py, mocked account selector = auth)
                       |
                       v
              ACCOUNT CONTEXT (authenticated_account_id, bound once per session)
                       |
                       v
         DETERMINISTIC ORCHESTRATOR  (src/agent/orchestrator.py)
                       |
        +--------------+---------------+
        |                              |
        v                              v
  Intent + entity extraction    Pending-action check
  (src/agent/intent.py,          (escalation confirm/
   regex/keywords, no LLM)        decline/re-ask,
        |                          src/agent/templates.py)
        v                              |
  Evidence assembly                    | ZERO LLM calls
  (src/agent/evidence.py)              | (fully deterministic,
   - account scope/security            |  structured content)
     (src/security/access_control.py)  |
   - structured lookups + calculations |
     (src/data/*)                      |
   - MiniLM + FAISS retrieval,         |
     authority filtering               |
     (src/retrieval/*)                 |
        |                              |
        v                              |
  Verified Evidence Package            |
        |                              |
   +----+----+                         |
   |         |                         |
   v         v                         |
 empty    has evidence                 |
   |         |                         |
   v         v                         |
 ZERO      ONE LLM CALL                |
 LLM       (src/agent/llm_client.py -  |
 calls      plain generate_content,    |
 (canned    no function calling,       |
 "can't     no tool loop)              |
 verify")     |                        |
   |          v                        |
   |     Natural-language response     |
   +----------+------------------------+
              v
         Streamlit (steps performed + sources shown, no hidden reasoning)
```

**When does the LLM get called?**

| Situation | LLM calls | Why |
|---|---|---|
| Grounded question with real evidence (cancellation, credit, SLA, product issue, general policy Q&A) | **1** | Needs natural-language synthesis of verified facts |
| Cross-account access request | **0** | Deterministic refusal — never let generation soften/leak a denial |
| No evidence found at all | **0** | Templated "I couldn't verify that" — avoids ever giving the LLM an empty package to fill with invented content |
| "Please escalate this issue" | **0** | Proposal is built from structured data (reason/priority/ticket) and rendered as a template |
| Escalation confirmation ("yes"/"no"/ambiguous) | **0** | Regex-classified; execution and response are both fully deterministic |

This replaced an earlier version that used Gemini function-calling with a multi-round tool loop
(the model calling `search_documents`, `lookup_order`, etc. itself, often 3-6 LLM round-trips per
question). That approach worked but was token-expensive — retrieval, lookups, and calculations
don't need an LLM in the loop; only the final phrasing does.

**The three separations this system is built around (Section 49 of the brief) still hold:**

| Layer | Storage | Access pattern |
|---|---|---|
| Knowledge (policies, agreements, SOPs, product docs) | FAISS vector index | Semantic search + metadata/authority filtering |
| Facts (accounts, orders, tickets) | pandas DataFrames from the Excel workbook | Deterministic, account-scoped Python functions — never embedded |
| Actions (escalations) | In-memory mock store | Two-step prepare → confirm → execute, gated by an explicit user confirmation |

## Source authority / data classification

Explicit registry in `config.py` (`DOCUMENT_REGISTRY`), reviewed by hand against the actual files:

| File | Status | Authority | Applies to | Indexed? |
|---|---|---|---|---|
| `01_Support_Policy_v3_CURRENT.pdf` | current | current_general_policy | all accounts | ✅ |
| `02_Support_Policy_v2_DEPRECATED.pdf` | **deprecated** | historical | — | ❌ excluded at build time |
| `03_Cancellation_and_Service_Credit_SOP_v4.pdf` | current | current_specific_sop | all accounts | ✅ |
| `04_Product_Operations_Guide_and_Known_Issues.pdf` | current | current_product_docs | all accounts | ✅ |
| `05_Northstar_Logistics_Enterprise_Agreement.pdf` | active | customer_specific_agreement | ACCT-001 only | ✅ (account-scoped) |
| `06_LumenWorks_Service_Agreement.pdf` | active | customer_specific_agreement | ACCT-002 only | ✅ (account-scoped) |
| `ParcelPilot_Assessment_Data.xlsx` | structured | n/a | per-row account_id | **not embedded** — queried via tools |

Authority is resolved **per subject**, not with one universal ranking (see `src/agent/prompts.py`):
SLA questions prefer contract > current policy > historical; cancellation/credit questions prefer
contract > current SOP > historical; product-behavior questions prefer current known issues/docs >
policy > historical. The deprecated policy is excluded from the active index entirely, so it can
never outrank the current one by accident. Another customer's agreement is filtered out at query
time even before ranking (`src/retrieval/retriever.py`), so it can never leak regardless of
similarity score.

## Access control

Enforced at the **data layer**, not the prompt (`src/security/access_control.py`,
`src/data/*_tools.py`). Every structured tool is bound, once per chat session, to the
authenticated account (`src/agent/tools.py::make_tool_functions`) — there is no tool parameter
that lets the model specify an arbitrary `account_id` for lookups. A lookup for an order/ticket
belonging to another account raises `AccessDeniedError` and returns a safe error to the model, it
never returns the data. Document retrieval applies the same filter: chunks tagged with
`customer_account = "ACCT-00X"` are only returned when the session's own account matches.

## Tools / capabilities (still 3+ distinct categories, no longer LLM-invoked)

The deterministic orchestrator (`src/agent/orchestrator.py`) calls these directly in Python -
they are no longer exposed to the LLM as function-calling tools, since the LLM's role is now
synthesis-only:

1. **Document search** — `src/retrieval/retriever.py::search_documents`, account-scoped, deprecated docs excluded, hybrid keyword/entity boost on top of semantic search (order/ticket/account IDs, carrier names, status strings).
2. **Structured lookup / calculation** — `src/data/{account,order,ticket}_tools.py`: account/order/ticket lookups plus deterministic fee/credit/SLA-breach math.
3. **State-changing action** — `src/actions/escalation.py::create_escalation`, invoked only from the deterministic confirmation branch in the orchestrator, never by the LLM.

## Intent detection (zero LLM calls)

`src/agent/intent.py` classifies each message into one of: `cancellation`, `service_credit`,
`sla`, `order_status`, `list_orders`, `ticket_status`, `list_tickets`, `account_info`, `escalate`,
or `general`, using keyword/regex matching — no model call. It also extracts order/ticket/known-issue
IDs and severities via regex, and detects follow-up pronoun references ("it", "that order") so a
prior turn's order/ticket ID can be reused for context-aware follow-ups without needing the LLM to
resolve coreference itself.

## Time handling

All "now" reasoning uses the dataset snapshot from the workbook README (`2026-08-16 11:00
Asia/Kolkata`), not the real clock (`config.DATASET_SNAPSHOT`). Cancellation-fee timing uses the
order's actual `cancellation_requested_at` when present (falling back to "if cancelled now" against
the snapshot when the customer hasn't requested one yet).

**Documented assumption:** the source policies say "business hours" / "business days" without
defining operating hours. I assumed Mon–Fri 09:00–18:00 Asia/Kolkata (9h/day), with "1 business
day" = 9 business hours, for SLA breach math (`src/data/ticket_tools.py`). This is the smallest
concrete assumption needed to make breach checks computable; it doesn't affect 24×7 targets, which
use pure elapsed calendar time.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Environment variables

Set via a local `.env` (loaded by `python-dotenv`) or exported directly:

```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash     # optional, this is the default
```

On Streamlit Community Cloud, set these in the app's **Secrets** panel instead (`.streamlit/secrets.toml`
format) — never commit a real key.

## Building the index

```bash
python scripts/build_index.py
```

This discovers the classified PDFs, extracts/cleans/chunks them (section-aware on the numbered
headings used throughout the source docs, falling back to character chunking with overlap for
oversized sections — see `config.CHUNK_SIZE` / `CHUNK_OVERLAP`), embeds them, and writes
`vectorstore/index.faiss` + `vectorstore/metadata.pkl`. The app loads this at startup and does not
rebuild it per request. Re-run this script (and re-commit the two output files) whenever the PDFs
in `data/knowledge_base/` change.

**Embedding model note:** the pipeline is written for `sentence-transformers/all-MiniLM-L6-v2`
(downloaded from Hugging Face on first use — this needs outbound internet access, which Streamlit
Community Cloud has). If that download isn't reachable (e.g. a fully offline sandbox), the pipeline
automatically falls back to a local TF-IDF vectorizer (`src/embeddings/embedder.py`) so indexing and
retrieval still work end-to-end; a small `vectorstore/fallback_vectorizer.pkl` is written in that
case and reused consistently at query time. This repo's committed index was built in that offline
fallback mode — expect noticeably better semantic ranking once you rebuild it with real internet
access and let it use MiniLM.

## Running locally

```bash
streamlit run app.py
```

Pick a demo customer from the sidebar (this is the mocked authentication — a real deployment would
replace this with actual login), then chat.

## Testing

```bash
python tests/test_access_control.py     # cross-account isolation
python tests/test_business_rules.py     # deterministic fee/credit/SLA math against the dataset
python tests/test_retrieval.py          # deprecated-doc exclusion, cross-account agreement isolation
python tests/test_orchestrator.py       # intent routing, evidence assembly, zero-vs-one-LLM-call decisions, escalation flow
```

All 25 tests pass without a `GEMINI_API_KEY`. `test_orchestrator.py` uses a scripted fake Gemini
client and explicitly asserts the call count for each scenario (e.g. `client.models.call_count ==
0` for access denial and the full escalation propose/confirm/decline flow, `== 1` for a grounded
question) — so a regression that accidentally reintroduces extra LLM calls will fail the test
suite, not just look slow in the UI.

## Manual test scenarios (verify via the running app with a real GEMINI_API_KEY)

1. *"Can Northstar cancel ORD-1001 without a cancellation fee?"* (as Northstar) — expect: yes, per
   the Northstar agreement's unconditional pre-pickup waiver, overriding the SOP's default ₹250 fee.
2. *"A pickup is three hours late because of carrier fault. Should I get a service credit?"* — no
   order ID given; expect the assistant to ask which order rather than guessing.
3. *"Can I cancel ORD-2002?"* (as LumenWorks) — expect: yes, but the default ₹250 SOP fee applies
   (LumenWorks' agreement explicitly does not waive it).
4. *"Why does my SwiftShip shipment still show BOOKED even though the driver collected it?"* (as
   Northstar, re: ORD-1002/TKT-504) — expect citation of KI-211 (webhook delay up to 20 min).
5. *"Why is my 4,200-row CSV upload failing?"* (as LumenWorks) — expect citation of KI-208
   (intermittent failures above ~3,000 rows despite the 5,000-row limit), **not** the incorrect
   historical guidance in TKT-451 ("Growth only supports 3,000 rows").
6. *"I need information about another customer's order."* — expect a clear refusal.
7. *"Please escalate this issue."* — expect a proposed action shown first, action only created after
   an explicit "yes"/"confirm" in the next message.
8. Ask something outside the data pack (e.g. "What's your refund policy for lost international
   shipments?") — expect "I couldn't verify that..." rather than an invented answer.

I traced scenarios 1, 3, 4, and 5 against the raw data by hand (see git history / dev notes) to
confirm the deterministic tools return the right numbers before trusting the LLM to reason over them.

## Known limitations

- Business-hours SLA math uses an assumed 09:00–18:00 Mon–Fri calendar (documented above); the
  source policies don't specify exact operating hours.
- The offline TF-IDF fallback embedder is meaningfully weaker than MiniLM at pure semantic
  similarity; the hybrid entity-boost (exact ID/keyword matching) compensates for the cases that
  matter most in this dataset (order/ticket/known-issue IDs), but a real deployment should rebuild
  the index with internet access so it uses MiniLM.
- The escalation "action" is a local in-memory mock (resets whenever the Streamlit process restarts)
  since no real ticketing system was provided to integrate with.
- Section-aware chunking splits on the numbered top-level headings each source document uses (e.g.
  "1. Support terms"); it does not further split multi-item sections like "2. Current known issues"
  (which contains both KI-208 and KI-211) into separate chunks. In practice retrieval still surfaces
  the whole section reliably, but a larger knowledge base would benefit from sub-heading-aware
  chunking.

## Future improvements

- Real authentication instead of the mocked account selector.
- Persist escalations outside process memory (e.g. a lightweight file-backed store) so they survive
  restarts, without introducing a full database for what's still an MVP.
- Sub-heading-aware chunking for sections with multiple enumerated items (e.g. individual known
  issues) once the knowledge base grows beyond a handful of one-page documents.
- Monthly aggregate service-credit cap tracking for Northstar (the agreement caps credits at
  ₹5,000/month; the current calculator returns a single order's credit and flags amounts over ₹1,000
  as needing manager approval, but doesn't yet track a running monthly total against the cap).

## Embedding/index consistency

The index and query encoder must use the same embedding model and vector dimension. The project now persists this choice in `vectorstore/embedder.json`. If the index is rebuilt with MiniLM, any stale `fallback_vectorizer.pkl` is removed automatically. If a query ever reports an embedding-dimension mismatch, run:

```bash
python scripts/build_index.py
```

Do not manually mix a MiniLM FAISS index with a TF-IDF fallback vectorizer.

## Deployment (Streamlit Community Cloud)

1. Push this repository to GitHub (the committed `vectorstore/index.faiss` + `metadata.pkl` ship
   with it — see `.gitignore` note).
2. On https://share.streamlit.io, select the repository, branch, and `app.py` as the entry point.
3. In the app's **Secrets** panel, add:
   ```toml
   GEMINI_API_KEY = "your_key_here"
   ```
4. Deploy. If you change the PDFs in `data/knowledge_base/`, rebuild the index locally
   (`python scripts/build_index.py`) and push the updated `vectorstore/` files — the deployed app
   does not rebuild embeddings on its own.

## Project structure

```
parcelpilot/
├── app.py                          Streamlit chat UI (mocked auth, tool/source expanders)
├── config.py                       Source registry, authority ranking, snapshot time, chunking params
├── requirements.txt
├── data/
│   ├── ParcelPilot_Assessment_Data.xlsx
│   └── knowledge_base/*.pdf
├── src/
│   ├── ingestion/                  PDF discovery, cleaning, section-aware chunking, metadata
│   ├── embeddings/                 MiniLM embedder with offline TF-IDF fallback
│   ├── retrieval/                  FAISS vector store + account/status-filtered, entity-boosted retriever
│   ├── data/                       workbook loader + account/order/ticket tools (deterministic calculations)
│   ├── agent/
│   │   ├── intent.py               regex/keyword intent + entity extraction (zero LLM calls)
│   │   ├── evidence.py             assembles the verified evidence package per intent
│   │   ├── templates.py            zero-LLM-call responses (access denial, escalation flow, empty evidence)
│   │   ├── llm_client.py           the ONE-call synthesis wrapper (no function calling)
│   │   ├── prompts.py              system prompt for the single synthesis call
│   │   └── orchestrator.py         entry point: ties it all together, owns session state
│   ├── actions/                    mock escalation store (prepare/execute split)
│   └── security/                   access_control.py — the one place cross-account decisions are made
├── scripts/build_index.py          run this to (re)build vectorstore/
├── vectorstore/                    index.faiss + metadata.pkl (committed, loaded at runtime)
└── tests/                          access control, business rules, retrieval, agent-loop orchestration
```
