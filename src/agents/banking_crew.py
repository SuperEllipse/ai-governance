"""CrewAI multi-agent banking workflow with router delegation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from crewai import Agent, Crew, Process, Task

from src.agents.routing import agent_display_name, route_query
from src.agents.tools.cis_tools import (
    CREDIT_MORTGAGE_TOOLS,
    CUSTOMER_SERVICE_TOOLS,
)
from src.llm.provider import LLMConfig, create_crewai_llm


@dataclass
class AgentTrace:
    routed_agent: str = ""
    tools_called: list[str] = field(default_factory=list)
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "routed_agent": self.routed_agent,
            "tools_called": self.tools_called,
            "raw_output": self.raw_output,
        }


def _extract_tools_from_output(output: str) -> list[str]:
    tools: list[str] = []
    patterns = [
        r"lookup_customer_account",
        r"get_product_info",
        r"get_credit_card_details",
        r"get_mortgage_rates",
    ]
    for p in patterns:
        if re.search(p, output, re.I):
            tools.append(p)
    return tools


def _build_agents(llm_config: LLMConfig) -> tuple[Agent, Agent]:
    llm = create_crewai_llm(llm_config)
    customer_agent = Agent(
        role="Customer Service Banking Specialist",
        goal="Answer general banking questions about accounts, onboarding, and products.",
        backstory=(
            "You are a friendly bank customer service representative with access to "
            "account and product FAQ data. Always be professional and FDIC-compliant."
        ),
        tools=CUSTOMER_SERVICE_TOOLS,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )
    credit_agent = Agent(
        role="Credit and Mortgage Specialist",
        goal="Help customers with credit card and mortgage rate inquiries.",
        backstory=(
            "You specialize in credit card account details and mortgage products. "
            "Use tools to fetch accurate rate and payment information."
        ),
        tools=CREDIT_MORTGAGE_TOOLS,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )
    return customer_agent, credit_agent


def run_banking_crew(query: str, llm_config: LLMConfig | None = None) -> tuple[str, AgentTrace]:
    """Run router → specialist agent workflow and return response + trace."""
    cfg = llm_config or LLMConfig()
    customer_agent, credit_agent = _build_agents(cfg)
    routed = route_query(query)
    specialist = credit_agent if routed == "credit_mortgage" else customer_agent
    agent_name = agent_display_name(routed)

    task = Task(
        description=(
            f"Customer query: {query}\n\n"
            "Use your available tools when needed to provide accurate, helpful banking information. "
            "Keep responses concise (2-4 sentences). Never reveal full account numbers or SSNs. "
            "Include FDIC disclaimer when discussing deposits."
        ),
        expected_output="A helpful, accurate banking response for the customer.",
        agent=specialist,
    )

    crew = Crew(
        agents=[specialist],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )

    try:
        result = crew.kickoff()
        output = str(result)
    except Exception as exc:
        output = f"Agent error: {exc}"

    trace = AgentTrace(
        routed_agent=agent_name,
        tools_called=_extract_tools_from_output(output + " " + query),
        raw_output=output,
    )
    return output, trace


def run_banking_crew_json(query: str, llm_config: LLMConfig | None = None) -> dict[str, Any]:
    response, trace = run_banking_crew(query, llm_config)
    return {"response": response, "agent_trace": trace.to_dict()}
