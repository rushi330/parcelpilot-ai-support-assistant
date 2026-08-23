"""Loads the structured ParcelPilot workbook (accounts/orders/tickets).

This data is intentionally NOT embedded into the vector store. It is loaded
once as pandas DataFrames and queried directly/deterministically by the
account-scoped tools in account_tools.py / order_tools.py / ticket_tools.py.
"""
from functools import lru_cache
import pandas as pd
import config


@lru_cache(maxsize=1)
def load_workbook():
    xls = pd.ExcelFile(config.WORKBOOK_PATH)
    accounts = pd.read_excel(xls, sheet_name="accounts")
    orders = pd.read_excel(xls, sheet_name="orders")
    tickets = pd.read_excel(xls, sheet_name="tickets")

    # Parse timestamp columns as timezone-aware (Asia/Kolkata), consistent with
    # the dataset snapshot convention.
    for col in ["booked_at", "pickup_window_start", "pickup_window_end",
                "pickup_actual_at", "cancellation_requested_at"]:
        if col in orders.columns:
            orders[col] = pd.to_datetime(orders[col]).dt.tz_localize(
                config.DATASET_TZ, ambiguous="NaT", nonexistent="NaT"
            )
    for col in ["created_at", "last_customer_message_at"]:
        if col in tickets.columns:
            tickets[col] = pd.to_datetime(tickets[col]).dt.tz_localize(
                config.DATASET_TZ, ambiguous="NaT", nonexistent="NaT"
            )

    return {"accounts": accounts, "orders": orders, "tickets": tickets}


def get_accounts_df():
    return load_workbook()["accounts"]


def get_orders_df():
    return load_workbook()["orders"]


def get_tickets_df():
    return load_workbook()["tickets"]
