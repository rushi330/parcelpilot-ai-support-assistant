"""ParcelPilot Customer Support Assistant - Streamlit chat UI."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st
import config
from src.data.workbook_loader import get_accounts_df
from src.agent.orchestrator import handle_turn, new_session_state
from src.actions.escalation import list_escalations_for_account

st.set_page_config(page_title="ParcelPilot Customer Support", page_icon="📦", layout="wide")

# ---------- Mocked authentication: demo account selector ----------
accounts_df = get_accounts_df()
account_options = {
    f"{row.account_name} ({row.account_id})": row.account_id
    for row in accounts_df.itertuples()
}

with st.sidebar:
    st.markdown("### 📦 ParcelPilot Customer Support")
    st.caption("Demo authentication - select the logged-in customer")
    selected_label = st.selectbox("Logged-in customer", list(account_options.keys()))
    selected_account_id = account_options[selected_label]
    selected_account_name = selected_label.split(" (")[0]

    acct_row = accounts_df[accounts_df.account_id == selected_account_id].iloc[0]
    st.markdown(
        f"**Account:** {selected_account_id}  \n"
        f"**Plan:** {acct_row.plan}  \n"
        f"**Status:** {acct_row.status}"
    )
    if isinstance(acct_row.contract_file, str) and acct_row.contract_file.strip():
        st.caption(f"Custom agreement on file: {acct_row.contract_file}")
    else:
        st.caption("No custom agreement - standard policies apply.")

    st.divider()
    if st.button("🔄 Reset conversation"):
        st.session_state.pop("messages", None)
        st.session_state.pop("conv_state", None)
        st.rerun()

    st.divider()
    st.caption(f"Dataset snapshot (reference time): {config.DATASET_SNAPSHOT.strftime('%Y-%m-%d %H:%M %Z')}")

    escalations = list_escalations_for_account(selected_account_id)
    if escalations:
        st.divider()
        st.markdown("**Your escalations**")
        for e in escalations:
            st.caption(f"{e['escalation_id']} - {e['priority']} - {e['status']}")

# ---------- Reset chat state when switching accounts ----------
if st.button("🔄 Reset conversation"):
    st.session_state["messages"] = []
    st.session_state["conv_state"] = new_session_state()
    st.rerun()

conv_state = st.session_state.get("conv_state", new_session_state())

st.title("ParcelPilot Customer Support")
st.caption(f"Chatting as **{selected_account_name}** ({selected_account_id})")

if not config.GEMINI_API_KEY:
    st.warning(
        "GEMINI_API_KEY is not configured. Set it as an environment variable or in "
        "Streamlit secrets (`.streamlit/secrets.toml` locally, or the Secrets panel on "
        "Streamlit Community Cloud) to start chatting."
    )

if "messages" not in st.session_state:
    st.session_state["messages"] = []

# ---------- Render conversation history ----------
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            if msg.get("steps"):
                label = "🔧 Steps performed" + ("" if msg.get("used_llm") else " (no LLM call needed)")
                with st.expander(label):
                    for t in msg["steps"]:
                        st.write(f"✓ {t}")
            if msg.get("sources"):
                with st.expander("📚 Sources"):
                    for s in msg["sources"]:
                        label = s["source"].replace("_", " ").replace(".pdf", "")
                        st.write(f"- {label} (page {s['page']}, section: {s.get('section') or '—'})")

# ---------- Chat input ----------
user_input = st.chat_input("Ask about your account, orders, tickets, cancellations, or policies...")

if user_input:
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Working on it..."):
            try:
                result = handle_turn(
                    selected_account_id, selected_account_name, user_input, conv_state
                )
                st.session_state["conv_state"] = result["session_state"]
                answer = result["answer"]
            except Exception as e:
                answer = (
                    "Sorry, something went wrong while processing your request. "
                    "Please try again. If the issue continues, please contact "
                    "ParcelPilot support."
                    )

                result = {
                    "steps": [],
                    "sources": [],
                    "used_llm": False,
                }
                print(f"[ERROR] {type(e).__name__}: {e}")
                    

        st.markdown(answer)
        if result.get("steps"):
            label = "🔧 Steps performed" + ("" if result.get("used_llm") else " (no LLM call needed)")
            with st.expander(label):
                for t in result["steps"]:
                    st.write(f"✓ {t}")
        if result.get("sources"):
            with st.expander("📚 Sources"):
                for s in result["sources"]:
                    label = s["source"].replace("_", " ").replace(".pdf", "")
                    st.write(f"- {label} (page {s['page']}, section: {s.get('section') or '—'})")

    st.session_state["messages"].append({
        "role": "assistant", "content": answer,
        "steps": result.get("steps", []),
        "sources": result.get("sources", []),
        "used_llm": result.get("used_llm", False),
    })
