"""Account-isolation enforcement.

This is the ONLY place cross-account access decisions are made. Every
structured-data tool must route through here. The LLM never sees this logic
and cannot bypass it - it only ever receives already-filtered results or an
explicit AccessDeniedError.
"""


class AccessDeniedError(Exception):
    """Raised when a request would expose data outside the authenticated account."""
    pass


def enforce_account_match(record_account_id: str, authenticated_account_id: str, resource: str = "record"):
    """Raise AccessDeniedError if the record does not belong to the authenticated account."""
    if record_account_id != authenticated_account_id:
        raise AccessDeniedError(
            f"Access denied: this {resource} does not belong to account "
            f"{authenticated_account_id}."
        )


def require_account_id(authenticated_account_id: str):
    if not authenticated_account_id:
        raise AccessDeniedError("No authenticated account context provided.")
