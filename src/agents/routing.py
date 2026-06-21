"""Lightweight intent router for banking agent delegation."""

from __future__ import annotations

import re
from typing import Literal

AgentName = Literal["customer_service", "credit_mortgage"]

CREDIT_KEYWORDS = re.compile(
    r"\b(credit\s*card|visa|mastercard|amex|apr|due\s*date|minimum\s*payment|"
    r"mortgage|refinance|interest\s*rate|30[\s-]*year|15[\s-]*year|arm|jumbo|loan\s*rate)\b",
    re.I,
)
ACCOUNT_KEYWORDS = re.compile(
    r"\b(checking|savings|account|balance|open\s*account|branch|fee|fraud|wire|deposit|onboard)\b",
    re.I,
)


def route_query(query: str) -> AgentName:
    """Classify query to the appropriate specialist agent."""
    if CREDIT_KEYWORDS.search(query):
        return "credit_mortgage"
    if ACCOUNT_KEYWORDS.search(query):
        return "customer_service"
    # Default to customer service for general banking
    return "customer_service"


def agent_display_name(agent: AgentName) -> str:
    return {
        "customer_service": "CustomerServiceAgent",
        "credit_mortgage": "CreditMortgageAgent",
    }[agent]
