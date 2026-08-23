"""Central configuration for the ParcelPilot Customer Support Assistant."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

try:
    import streamlit as st
    _SECRETS = st.secrets
except Exception:
    _SECRETS = {}

def _get_secret(key: str, default: str = "") -> str:
    if key in os.environ:
        return os.environ[key]
    try:
        if key in _SECRETS:
            return _SECRETS[key]
    except Exception:
        pass
    return default

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_DIR = BASE_DIR / "data" / "knowledge_base"
WORKBOOK_PATH = BASE_DIR / "data" / "ParcelPilot_Assessment_Data.xlsx"
VECTORSTORE_DIR = BASE_DIR / "vectorstore"
FAISS_INDEX_PATH = VECTORSTORE_DIR / "index.faiss"
METADATA_PATH = VECTORSTORE_DIR / "metadata.pkl"
EMBEDDER_INFO_PATH = VECTORSTORE_DIR / "embedder.json"

# --- LLM ---
GEMINI_API_KEY = _get_secret("GEMINI_API_KEY", "")
GEMINI_MODEL = _get_secret("GEMINI_MODEL", "gemini-3.6-flash")

# --- Embeddings ---
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# --- Chunking (configurable, see README for tuning notes) ---
CHUNK_SIZE = 900       # characters
CHUNK_OVERLAP = 150    # characters

# --- Retrieval ---
TOP_K = 5

# --- Time handling ---
# The dataset is frozen at this snapshot time. All time-based reasoning about
# accounts/orders/tickets must use this, never the real system clock.
DATASET_TZ = ZoneInfo("Asia/Kolkata")
import datetime as _dt
DATASET_SNAPSHOT = _dt.datetime(2026, 8, 16, 11, 0, tzinfo=DATASET_TZ)

# --- Document source registry ---
# Explicit, human-reviewed classification of every source file.
# This drives retrieval filtering and authority resolution.
DOCUMENT_REGISTRY = {
    "01_Support_Policy_v3_CURRENT.pdf": {
        "document_type": "support_policy",
        "status": "current",
        "authority": "current_general_policy",
        "customer_account": None,  # applies to all
        "topic": "sla",
        "active_for_retrieval": True,
    },
    "02_Support_Policy_v2_DEPRECATED.pdf": {
        "document_type": "support_policy",
        "status": "deprecated",
        "authority": "historical",
        "customer_account": None,
        "topic": "sla",
        "active_for_retrieval": False,  # excluded from active index
    },
    "03_Cancellation_and_Service_Credit_SOP_v4.pdf": {
        "document_type": "cancellation_sop",
        "status": "current",
        "authority": "current_specific_sop",
        "customer_account": None,
        "topic": "cancellation_and_credit",
        "active_for_retrieval": True,
    },
    "04_Product_Operations_Guide_and_Known_Issues.pdf": {
        "document_type": "product_docs",
        "status": "current",
        "authority": "current_product_docs",
        "customer_account": None,
        "topic": "product_and_known_issues",
        "active_for_retrieval": True,
    },
    "05_Northstar_Logistics_Enterprise_Agreement.pdf": {
        "document_type": "customer_agreement",
        "status": "active",
        "authority": "customer_specific_agreement",
        "customer_account": "ACCT-001",
        "topic": "contract",
        "active_for_retrieval": True,
    },
    "06_LumenWorks_Service_Agreement.pdf": {
        "document_type": "customer_agreement",
        "status": "active",
        "authority": "customer_specific_agreement",
        "customer_account": "ACCT-002",
        "topic": "contract",
        "active_for_retrieval": True,
    },
}

# Numeric authority rank used for tie-breaking / sorting (lower = stronger)
AUTHORITY_RANK = {
    "customer_specific_agreement": 0,
    "current_specific_sop": 1,
    "current_general_policy": 2,
    "current_product_docs": 3,
    "historical": 4,
}
