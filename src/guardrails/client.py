"""Guardrails client: unguarded, embedded LLMRails, and centralized server modes."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from src.guardrails.config_composer import compose_config
from src.guardrails.violation_parser import ViolationRecord, parse_guardrails_output
from src.llm.provider import LLMConfig, SafetyModelConfig, default_llm_config

logger = logging.getLogger(__name__)

GuardrailsMode = Literal["unguarded", "embedded", "server"]

# Must match the ``base/`` subfolder under GUARDRAILS_CONFIG and server DEFAULT_CONFIG_ID.
DEFAULT_GUARDRAILS_CONFIG_ID = "base"

GUARDRAILS_OPTIONS = {
    "output_vars": [
        "triggered_input_rail",
        "triggered_output_rail",
        "allowed",
    ],
    "log": {"activated_rails": True, "llm_calls": True},
}

_INTERNAL_ERROR_MARKERS = (
    "internal error has occurred",
    "an internal error",
    "internal server error",
)

_INFRASTRUCTURE_ERROR_MARKERS = (
    "tcptransport",
    "handler is closed",
    "event loop is closed",
    "stale event loop",
    "connection error",
    "unable to perform operation",
    "error invoking llm",
)


def _label_guardrails_provider(log_data: dict[str, Any], llm_config: LLMConfig) -> dict[str, Any]:
    """Cosmetic: show CAIIS label in guardrails logs instead of generic openai."""
    if llm_config.provider != "caiis":
        return log_data
    label = "Cloudera AI Inference Service"
    calls = log_data.get("llm_calls")
    if isinstance(calls, list):
        for entry in calls:
            if isinstance(entry, dict) and entry.get("llm_provider_name") == "openai":
                entry["llm_provider_name"] = label
    return log_data


def _merge_guardrails_logs(
    base: dict[str, Any] | None,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge activated_rails and llm_calls from two guardrails log payloads."""
    if not base:
        return extra or {}
    if not extra:
        return base
    merged = dict(base)
    base_rails = list(merged.get("activated_rails") or [])
    extra_rails = list(extra.get("activated_rails") or [])
    merged["activated_rails"] = base_rails + extra_rails
    base_calls = list(merged.get("llm_calls") or [])
    extra_calls = list(extra.get("llm_calls") or [])
    if base_calls or extra_calls:
        merged["llm_calls"] = base_calls + extra_calls
    return merged


DEFAULT_BLOCK_REFUSAL = (
    "I'm sorry, I can't help with that request. "
    "Please ask about retail banking services such as accounts, cards, or mortgages."
)


def _friendly_block_refusal(
    query: str,
    triggered_rail: str | None,
    log_data: dict[str, Any],
    output_vars: dict[str, Any] | None = None,
) -> str:
    """Build a user-facing refusal when guardrails blocked the request."""
    from src.guardrails.violation_parser import extract_policy_reason

    if output_vars and output_vars.get("policy_reason"):
        return DEFAULT_BLOCK_REFUSAL

    rail = triggered_rail or "blocked"
    rail_type = "output" if output_vars and output_vars.get("triggered_output_rail") else "input"
    reason, _ = extract_policy_reason(rail, rail_type, query, log_data)
    if reason:
        return DEFAULT_BLOCK_REFUSAL
    return DEFAULT_BLOCK_REFUSAL


def _is_successful_policy_block(
    output_vars: dict[str, Any] | None,
    log_data: dict[str, Any] | None = None,
) -> bool:
    """True when guardrails metadata indicates an intentional policy block."""
    output_vars = output_vars or {}
    if output_vars.get("allowed") is False:
        return True
    if output_vars.get("triggered_input_rail") or output_vars.get("triggered_output_rail"):
        return True
    log_data = log_data or {}
    activated = log_data.get("activated_rails") or []
    if activated:
        if isinstance(activated, dict):
            for info in activated.values():
                if isinstance(info, dict) and info.get("stop"):
                    return True
        elif isinstance(activated, list) and len(activated) > 0:
            return True
    return False


def _looks_like_internal_error(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _INTERNAL_ERROR_MARKERS)


def _looks_like_infrastructure_error(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _INFRASTRUCTURE_ERROR_MARKERS)


def _looks_like_raw_generation_response(text: str) -> bool:
    return text.startswith("response=[") and "llm_output=" in text


def _prepare_worker_event_loop() -> None:
    """Give each embedded guardrails check a fresh asyncio loop in the worker thread.

    Streamlit calls ``asyncio.run()`` per request, which closes the main loop and
    any httpx transports bound to it. Reusing a stale loop in the default thread
    pool causes ``TCPTransport closed`` errors on subsequent NeMo LLM calls.
    """
    asyncio.set_event_loop(asyncio.new_event_loop())


def _exception_text(exc: Exception) -> str:
    """Normalize exception text, including NeMo LLMCallException detail."""
    parts = [str(exc)]
    detail = getattr(exc, "detail", None)
    if detail:
        parts.append(str(detail))
    inner = getattr(exc, "inner_exception", None)
    if inner and str(inner) not in parts[0]:
        parts.append(str(inner))
    if exc.__cause__ and str(exc.__cause__) not in " ".join(parts):
        parts.append(str(exc.__cause__))
    return " ".join(parts)


def _content_from_messages_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list) and payload:
        last = payload[-1]
        if isinstance(last, dict):
            return str(last.get("content", ""))
        return str(last)
    return str(payload or "")


def _extract_response_content(response: Any) -> str:
    """Normalize NeMo Guardrails generate/check responses to plain text."""
    if response is None:
        return ""

    # RailsResult from check/check_async
    if hasattr(response, "content") and hasattr(response, "status"):
        return str(getattr(response, "content", "") or "")

    if isinstance(response, dict):
        if "content" in response and "status" in response:
            return str(response.get("content") or "")
        if "response" in response:
            return _content_from_messages_payload(response["response"])
        if "content" in response:
            return str(response["content"])
        choices = response.get("choices")
        if choices:
            message = choices[0].get("message", {})
            return str(message.get("content", ""))

    if hasattr(response, "model_dump"):
        data = response.model_dump()
        if "content" in data and "status" in data:
            return str(data.get("content") or "")
        if "response" in data:
            return _content_from_messages_payload(data["response"])

    if hasattr(response, "response"):
        return _content_from_messages_payload(response.response)

    text = str(response)
    if _looks_like_raw_generation_response(text):
        return "I'm sorry, an internal error has occurred."
    return text


def _ensure_text_response(value: Any) -> str:
    """Guarantee a user-facing string, never a GenerationResponse repr."""
    if isinstance(value, str):
        text = value
    else:
        text = _extract_response_content(value)
    if _looks_like_raw_generation_response(text):
        return "I'm sorry, an internal error has occurred."
    return text


def _extract_generation_metadata(response: Any) -> tuple[dict, dict]:
    """Extract log and output_vars from a GenerationResponse-like object."""
    if not hasattr(response, "model_dump") and not isinstance(response, dict):
        return {}, {}

    data = response.model_dump() if hasattr(response, "model_dump") else response
    log_data = data.get("log") or {}
    if hasattr(log_data, "model_dump"):
        log_data = log_data.model_dump()
    output_vars = data.get("output_data") or {}
    if not output_vars:
        output_vars = {
            k: data.get(k)
            for k in ("triggered_input_rail", "triggered_output_rail", "allowed")
            if k in data
        }
    return log_data or {}, output_vars or {}


@dataclass
class GuardedResult:
    query: str
    unguarded_response: str
    guarded_response: str
    violations: list[ViolationRecord] = field(default_factory=list)
    agent_trace: dict[str, Any] = field(default_factory=dict)
    mode: str = "unguarded"
    policies: list[str] = field(default_factory=list)
    blocked: bool = False
    guardrails_log: dict[str, Any] = field(default_factory=dict)
    output_vars: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "unguarded_response": self.unguarded_response,
            "guarded_response": self.guarded_response,
            "violations": [v.to_dict() for v in self.violations],
            "agent_trace": self.agent_trace,
            "mode": self.mode,
            "policies": self.policies,
            "blocked": self.blocked,
            "guardrails_log": self.guardrails_log,
            "output_vars": self.output_vars,
        }


class GuardrailsClient:
    def __init__(
        self,
        llm_config: LLMConfig | None = None,
        safety_config: SafetyModelConfig | None = None,
        server_url: str = "http://localhost:8000",
    ):
        self.llm_config = llm_config or default_llm_config()
        self.safety_config = safety_config or SafetyModelConfig()
        self.server_url = server_url.rstrip("/")

    def _create_embedded_rails(self, policies: list[str]) -> Any:
        from nemoguardrails import LLMRails, RailsConfig

        config_path = compose_config(policies, self.llm_config, self.safety_config)
        config = RailsConfig.from_path(str(config_path))
        return LLMRails(config)

    async def run_query(
        self,
        query: str,
        policies: list[str] | None = None,
        mode: GuardrailsMode = "embedded",
        category: str = "",
        expected_policy: str = "",
        run_id: str = "",
    ) -> GuardedResult:
        policies = policies or []
        from src.agents.banking_crew import run_banking_crew

        unguarded_resp, trace = await asyncio.to_thread(
            run_banking_crew, query, self.llm_config
        )
        trace_dict = trace.to_dict()

        if mode == "unguarded" or not policies:
            return GuardedResult(
                query=query,
                unguarded_response=unguarded_resp,
                guarded_response=unguarded_resp,
                agent_trace=trace_dict,
                mode="unguarded",
                policies=policies,
            )

        if mode == "embedded":
            guarded_resp, log_data, output_vars, blocked = await self._run_embedded(
                query,
                policies,
                unguarded_resp,
            )
        elif mode == "server":
            guarded_resp, log_data, output_vars, blocked = await self._run_server(
                query, policies, unguarded_resp
            )
        else:
            guarded_resp, log_data, output_vars, blocked = unguarded_resp, {}, {}, False

        guarded_resp = _ensure_text_response(guarded_resp)

        violations = parse_guardrails_output(
            query=query,
            response=guarded_resp,
            log_data=log_data,
            output_vars=output_vars,
            policies=policies,
            category=category,
            expected_policy=expected_policy,
            agent=trace_dict.get("routed_agent", ""),
            unguarded_response=unguarded_resp,
            run_id=run_id,
        )

        return GuardedResult(
            query=query,
            unguarded_response=unguarded_resp,
            guarded_response=guarded_resp,
            violations=violations,
            agent_trace=trace_dict,
            mode=mode,
            policies=policies,
            blocked=blocked,
            guardrails_log=log_data,
            output_vars=output_vars,
        )

    async def _run_embedded(
        self,
        query: str,
        policies: list[str],
        agent_response: str,
    ) -> tuple[str, dict, dict, bool]:
        try:
            return await asyncio.to_thread(
                self._run_embedded_sync,
                query,
                policies,
                agent_response,
            )
        except Exception as exc:
            logger.exception("Embedded guardrails error")
            return self._embedded_error_result(agent_response, exc)

    def _embedded_error_result(
        self,
        agent_response: str,
        exc: Exception,
    ) -> tuple[str, dict, dict, bool]:
        err_text = _exception_text(exc)
        if _looks_like_infrastructure_error(err_text):
            return (
                agent_response,
                {},
                {
                    "allowed": True,
                    "guardrails_error": (
                        "Safety check could not complete due to a connection issue. "
                        "The unguarded response is shown for comparison."
                    ),
                },
                False,
            )
        return (
            "Request blocked by safety policy.",
            {},
            {"allowed": False, "guardrails_error": err_text},
            True,
        )

    def _embedded_generate_options(self, rail_types: list[Any]) -> dict[str, Any]:
        """Generation options for embedded checks with violation-reason logging."""
        return {
            "rails": [r.value for r in rail_types],
            "output_vars": GUARDRAILS_OPTIONS["output_vars"],
            "log": GUARDRAILS_OPTIONS["log"],
        }

    def _embedded_generate_check(
        self,
        rails: Any,
        messages: list[dict[str, str]],
        rail_types: list[Any],
    ) -> tuple[Any, dict[str, Any], dict[str, Any], str | None, str]:
        """Run input/output rails via generate_async and return response + metadata."""
        from nemoguardrails.rails.llm.llmrails import (
            _get_blocking_rail,
            _get_last_response_content,
        )

        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(
            rails.generate_async(
                messages=messages,
                options=self._embedded_generate_options(rail_types),
            )
        )
        log_data, output_vars = _extract_generation_metadata(response)
        blocking_rail = _get_blocking_rail(response)
        content = _ensure_text_response(_get_last_response_content(response))
        return response, log_data, output_vars, blocking_rail, content

    def _run_embedded_sync(
        self,
        query: str,
        policies: list[str],
        agent_response: str,
    ) -> tuple[str, dict, dict, bool]:
        try:
            from nemoguardrails.rails.llm.options import RailType
        except ImportError as exc:
            return (
                f"NeMo Guardrails not installed: {exc}",
                {},
                {},
                False,
            )

        try:
            _prepare_worker_event_loop()
            if self.safety_config.mode == "llama_guard":
                blocked = self._llama_guard_input_block(query)
                if blocked:
                    return blocked

            rails = self._create_embedded_rails(policies)
            log_data: dict[str, Any] = {}
            output_vars: dict[str, Any] = {"allowed": True}

            _, input_log, input_vars, input_blocking, input_content = (
                self._embedded_generate_check(
                    rails,
                    [{"role": "user", "content": query}],
                    [RailType.INPUT],
                )
            )
            log_data = _label_guardrails_provider(input_log, self.llm_config)
            if input_blocking:
                output_vars = {
                    "allowed": False,
                    "triggered_input_rail": input_blocking,
                    **{k: v for k, v in input_vars.items() if k in output_vars or k.startswith("triggered_")},
                }
                output_vars["allowed"] = False
                output_vars["triggered_input_rail"] = input_blocking
                _, _ = self._resolve_rail_result_content(
                    input_content, agent_response, rail_kind="input", blocked=True
                )
                return input_content, log_data, output_vars, True

            _, output_log, output_vars_raw, output_blocking, output_content = (
                self._embedded_generate_check(
                    rails,
                    [
                        {"role": "user", "content": query},
                        {"role": "assistant", "content": agent_response},
                    ],
                    [RailType.OUTPUT],
                )
            )
            log_data = _label_guardrails_provider(
                _merge_guardrails_logs(log_data, output_log),
                self.llm_config,
            )
            if output_blocking:
                output_vars = {
                    "allowed": False,
                    "triggered_output_rail": output_blocking,
                    **{k: v for k, v in output_vars_raw.items() if k.startswith("triggered_")},
                }
                _, _ = self._resolve_rail_result_content(
                    output_content, agent_response, rail_kind="output", blocked=True
                )
                return output_content, log_data, output_vars, True

            if self.safety_config.mode == "llama_guard":
                blocked = self._llama_guard_output_block(agent_response)
                if blocked:
                    return blocked

            if output_content != agent_response:
                output_vars = {"allowed": True}
                return output_content, log_data, output_vars, False

            return agent_response, log_data, output_vars, False
        except Exception as exc:
            logger.exception("Embedded guardrails sync check failed")
            return self._embedded_error_result(agent_response, exc)

    def _resolve_rail_result_content(
        self,
        content: str,
        agent_response: str,
        rail_kind: str,
        blocked: bool,
    ) -> tuple[str, bool]:
        """Map generated rail content to display text and blocked flag."""
        if _looks_like_infrastructure_error(content):
            logger.warning(
                "Guardrails %s check hit connection error",
                rail_kind,
            )
            raise RuntimeError(content)
        if _looks_like_internal_error(content) or _looks_like_raw_generation_response(
            content
        ):
            logger.warning(
                "Guardrails %s check returned internal error; using agent response",
                rail_kind,
            )
            return agent_response, False
        if blocked:
            return content, True
        if content != agent_response:
            return content, False
        return agent_response, False

    def _llama_guard_input_block(
        self, query: str
    ) -> tuple[str, dict[str, Any], dict[str, Any], bool] | None:
        from src.guardrails.llama_guard import block_refusal_for_category, check_llama_guard

        result = check_llama_guard(query, self.safety_config, context_label="user")
        if result.error:
            logger.warning("Llama Guard input check skipped: %s", result.error)
            return None
        if not result.blocked:
            return None
        refusal, reason = block_refusal_for_category(result.category)
        log_data = {
            "llama_guard": {
                "input": result.raw_response,
                "category": result.category,
            }
        }
        output_vars = {
            "allowed": False,
            "triggered_input_rail": "llama guard input",
            "policy_reason": reason,
        }
        return refusal, log_data, output_vars, True

    def _llama_guard_output_block(
        self, agent_response: str
    ) -> tuple[str, dict[str, Any], dict[str, Any], bool] | None:
        from src.guardrails.llama_guard import block_refusal_for_category, check_llama_guard

        result = check_llama_guard(
            agent_response, self.safety_config, context_label="assistant"
        )
        if result.error:
            logger.warning("Llama Guard output check skipped: %s", result.error)
            return None
        if not result.blocked:
            return None
        refusal, reason = block_refusal_for_category(result.category)
        log_data = {
            "llama_guard": {
                "output": result.raw_response,
                "category": result.category,
            }
        }
        output_vars = {
            "allowed": False,
            "triggered_output_rail": "llama guard output",
            "policy_reason": reason,
        }
        return refusal, log_data, output_vars, True

    def _resolve_rail_result(
        self,
        result: Any,
        agent_response: str,
        rail_kind: str,
    ) -> tuple[str, bool]:
        """Map a RailsResult to display text and blocked flag."""
        from nemoguardrails.rails.llm.options import RailStatus

        content = _ensure_text_response(result)
        if _looks_like_infrastructure_error(content):
            logger.warning(
                "Guardrails %s check hit connection error",
                rail_kind,
            )
            raise RuntimeError(content)
        if _looks_like_internal_error(content) or _looks_like_raw_generation_response(
            content
        ):
            logger.warning(
                "Guardrails %s check returned internal error; using agent response",
                rail_kind,
            )
            return agent_response, False

        if result.status == RailStatus.BLOCKED:
            return content, True
        if result.status == RailStatus.MODIFIED:
            return content, False
        return agent_response, False

    async def _run_server(
        self,
        query: str,
        policies: list[str],
        agent_context: str,
    ) -> tuple[str, dict, dict, bool]:
        if self.safety_config.mode == "llama_guard":
            blocked = await asyncio.to_thread(self._llama_guard_input_block, query)
            if blocked:
                return blocked

        url = f"{self.server_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.llm_config.api_key:
            headers["Authorization"] = f"Bearer {self.llm_config.api_key}"

        # Input rails should judge the user query only. Agent draft text belongs in
        # embedded output checks, not mixed into the user message for server mode.
        payload = {
            "model": self.llm_config.model,
            "messages": [{"role": "user", "content": query}],
            "guardrails": {
                "config_id": DEFAULT_GUARDRAILS_CONFIG_ID,
                "options": GUARDRAILS_OPTIONS,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.ConnectError:
            return (
                "Guardrails server not reachable at "
                f"{self.server_url}. Start with scripts/start_guardrails_server.sh",
                {},
                {},
                False,
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            return (
                f"Server guardrails error ({exc.response.status_code}): {detail}",
                {},
                {},
                False,
            )
        except Exception as exc:
            return f"Server guardrails error: {exc}", {}, {}, False

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = _ensure_text_response(message.get("content", "") or message)
        guardrails_meta = data.get("guardrails", {}) or message.get("guardrails", {})
        log_data = _label_guardrails_provider(
            guardrails_meta.get("log", {}),
            self.llm_config,
        )
        output_vars = guardrails_meta.get("output_data", guardrails_meta.get("output_vars", {}))

        triggered_rail = output_vars.get("triggered_input_rail") or output_vars.get(
            "triggered_output_rail"
        )
        allowed = output_vars.get("allowed", True)
        is_block = _is_successful_policy_block(output_vars, log_data)

        if is_block:
            if (
                _looks_like_internal_error(content)
                or not content.strip()
                or content.strip().lower().startswith("i'm sorry, an internal error")
            ):
                content = _friendly_block_refusal(query, triggered_rail, log_data, output_vars)
            return content, log_data, output_vars, True

        if self.safety_config.mode == "llama_guard":
            blocked = await asyncio.to_thread(
                self._llama_guard_output_block, agent_context
            )
            if blocked:
                return blocked

        if _looks_like_internal_error(content):
            return (
                "Guardrails server returned an internal error during safety checks. "
                "Check guardrails server logs for LLMCallException details "
                "(common with reasoning models when self_check misparses Yes/No). "
                "Ensure CAIIS_MAX_TOKENS>=1024 and restart the guardrails server.",
                log_data,
                {"allowed": False, "guardrails_error": content},
                False,
            )
        return content, log_data, output_vars, not allowed


async def run_query(
    query: str,
    policies: list[str] | None = None,
    mode: GuardrailsMode = "embedded",
    llm_config: LLMConfig | None = None,
    safety_config: SafetyModelConfig | None = None,
    server_url: str = "http://localhost:8000",
    **kwargs: Any,
) -> GuardedResult:
    client = GuardrailsClient(llm_config, safety_config, server_url)
    return await client.run_query(query, policies, mode, **kwargs)
