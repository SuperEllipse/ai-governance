"""CIS lookup tools backed by dummy JSON datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crewai.tools import tool

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "dummy_cis"


def _load_json(filename: str) -> list[dict[str, Any]] | dict[str, Any]:
    path = DATA_DIR / filename
    with path.open() as f:
        return json.load(f)


@tool("lookup_customer_account")
def lookup_customer_account(customer_id: str) -> str:
    """Look up checking/savings account details for a customer by customer ID (e.g. CUST-1001)."""
    accounts = _load_json("accounts.json")
    customers = _load_json("customers.json")
    customer = next((c for c in customers if c["customer_id"] == customer_id), None)
    if not customer:
        return f"No customer found with ID {customer_id}."
    cust_accounts = [a for a in accounts if a["customer_id"] == customer_id]
    if not cust_accounts:
        return f"Customer {customer['name']} has no accounts on file."
    lines = [f"Customer: {customer['name']} ({customer['tier']} tier)"]
    for acct in cust_accounts:
        lines.append(
            f"- {acct['type'].title()} {acct['account_id']}: "
            f"${acct['balance']:,.2f} balance, status={acct['status']}, "
            f"opened {acct['open_date']}"
        )
    return "\n".join(lines)


@tool("get_product_info")
def get_product_info(topic: str) -> str:
    """Get banking product FAQ info. Topics: open_account, branch_hours, fees, savings, fraud, mobile_banking, wire_transfer, loan_application."""
    faq = _load_json("product_faq.json")
    topic_lower = topic.lower().replace(" ", "_")
    for entry in faq:
        if entry["topic"] == topic_lower or topic_lower in entry["question"].lower():
            return f"Q: {entry['question']}\nA: {entry['answer']}"
    available = ", ".join(e["topic"] for e in faq)
    return f"No FAQ found for '{topic}'. Available topics: {available}"


@tool("get_credit_card_details")
def get_credit_card_details(last_four: str) -> str:
    """Get credit card details by last four digits of the card number (e.g. 4521)."""
    cards = _load_json("credit_cards.json")
    card = next((c for c in cards if c["last_four"] == last_four), None)
    if not card:
        return f"No credit card found ending in {last_four}."
    return (
        f"Card: {card['card_type']} ending in {card['last_four']}\n"
        f"Balance: ${card['balance']:,.2f}\n"
        f"Due date: {card['due_date']}\n"
        f"Minimum payment: ${card['min_payment']:,.2f}\n"
        f"APR: {card['apr']}%"
    )


@tool("get_mortgage_rates")
def get_mortgage_rates() -> str:
    """Get current mortgage rates including 15yr/30yr fixed and ARM products."""
    data = _load_json("mortgage_rates.json")
    lines = [f"Mortgage rates as of {data['last_updated']}:"]
    for name, rate in data["rates"].items():
        lines.append(
            f"- {name.replace('_', ' ').title()}: {rate['rate']}% rate, "
            f"{rate['apr']}% APR, {rate['points']} points"
        )
    lines.append(data["disclaimer"])
    return "\n".join(lines)


CUSTOMER_SERVICE_TOOLS = [lookup_customer_account, get_product_info]
CREDIT_MORTGAGE_TOOLS = [get_credit_card_details, get_mortgage_rates]
