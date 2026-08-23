"""Account-scoped structured lookups for account records."""
from src.data.workbook_loader import get_accounts_df
from src.security.access_control import require_account_id


def lookup_account(account_id: str) -> dict:
    """Look up the authenticated customer's own account.

    A customer may only ever look up their OWN account (account_id must equal
    the authenticated context - enforced by caller passing the same value).
    """
    require_account_id(account_id)
    df = get_accounts_df()
    row = df[df["account_id"] == account_id]
    if row.empty:
        return {"found": False, "error": f"No account found for {account_id}"}
    r = row.iloc[0]
    return {
        "found": True,
        "account_id": r["account_id"],
        "account_name": r["account_name"],
        "plan": r["plan"],
        "status": r["status"],
        "premium_support": bool(r["premium_support"]),
        "has_custom_contract": bool(isinstance(r["contract_file"], str) and r["contract_file"].strip()),
        "notes": r["notes"] if isinstance(r["notes"], str) else None,
    }
