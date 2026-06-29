"""Build CAIIS OpenAI-compatible base URLs from CAII-compliant env vars.

Cloudera AI Inference Application env values must start and end with alphanumerics
and may only contain ``[a-zA-Z0-9-_.]`` in between. Full URLs like
``CAIIS_BASE_URL=https://ml-....cloudera.site/namespaces/...`` are rejected in the
Application UI; use ``CAIIS_HOST`` + ``CAIIS_ENDPOINT`` (and optional namespace/path)
instead.

Legacy ``CAIIS_BASE_URL`` (and ``LLAMA_GUARD_BASE_URL``, ``GUARDRAILS_SERVER_URL``)
remain supported for local ``.env`` files and CDSW sessions.
"""

from __future__ import annotations

import os

CAIIS_DEFAULT_NAMESPACE = "serving-default"
CAIIS_DEFAULT_API_PATH = "openai"
CAIIS_DEFAULT_MODEL = "nvidia/nemotron-3-nano"
LLAMA_GUARD_DEFAULT_ENDPOINT = "llama-guard-3"
LLAMA_GUARD_DEFAULT_MODEL = "meta-llama/Llama-Guard-3-8B"

CAIIS_PLACEHOLDER_MARKERS = ("YOUR-DOMAIN", "YOUR-MODEL", "YOUR-ENDPOINT", "YOUR-CLUSTER-ID")
LLAMA_GUARD_PLACEHOLDER_MARKERS = CAIIS_PLACEHOLDER_MARKERS


def _strip_slashes(value: str) -> str:
    return value.strip().strip("/")


def _resolve_slash_model(
    explicit_key: str,
    org_key: str,
    name_key: str,
    default: str,
) -> str:
    """Resolve ``org/name`` model ids from CAII-compliant env vars.

    Prefer the full ``explicit_key`` value (allowed in local ``.env`` / CDSW);
    otherwise join ``org_key`` and ``name_key`` when both are set.
    """
    explicit = os.getenv(explicit_key, "").strip()
    if explicit:
        return explicit

    org = os.getenv(org_key, "").strip()
    name = os.getenv(name_key, "").strip()
    if org and name:
        return f"{org}/{name}"

    return default


def resolve_caiis_model() -> str:
    """Prefer ``CAIIS_MODEL``; else ``{CAIIS_MODEL_ORG}/{CAIIS_MODEL_NAME}``."""
    return _resolve_slash_model(
        "CAIIS_MODEL",
        "CAIIS_MODEL_ORG",
        "CAIIS_MODEL_NAME",
        CAIIS_DEFAULT_MODEL,
    )


def resolve_llama_guard_model() -> str:
    """Prefer ``LLAMA_GUARD_MODEL``; else ``{LLAMA_GUARD_MODEL_ORG}/{LLAMA_GUARD_MODEL_NAME}``."""
    return _resolve_slash_model(
        "LLAMA_GUARD_MODEL",
        "LLAMA_GUARD_MODEL_ORG",
        "LLAMA_GUARD_MODEL_NAME",
        LLAMA_GUARD_DEFAULT_MODEL,
    )


def build_caiis_base_url(
    host: str,
    endpoint: str,
    *,
    namespace: str = CAIIS_DEFAULT_NAMESPACE,
    api_path: str | None = CAIIS_DEFAULT_API_PATH,
    scheme: str = "https",
) -> str:
    """Build ``https://{host}/namespaces/{ns}/endpoints/{endpoint}/[{api_path}/]v1``."""
    host = host.strip()
    endpoint = _strip_slashes(endpoint)
    namespace = _strip_slashes(namespace)
    path_segment = _strip_slashes(api_path) if api_path else ""

    segments = [f"{scheme}://{host}", "namespaces", namespace, "endpoints", endpoint]
    if path_segment:
        segments.extend([path_segment, "v1"])
    else:
        segments.append("v1")
    return "/".join(segments)


def _resolve_api_path(env_key: str, default: str | None) -> str:
    raw = os.getenv(env_key)
    if raw is None:
        return default or ""
    return raw.strip()


def resolve_caiis_base_url() -> str:
    """Prefer ``CAIIS_BASE_URL``; otherwise build from ``CAIIS_HOST`` + ``CAIIS_ENDPOINT``."""
    explicit = os.getenv("CAIIS_BASE_URL", "").strip()
    if explicit:
        return explicit

    host = os.getenv("CAIIS_HOST", "").strip()
    endpoint = os.getenv("CAIIS_ENDPOINT", "").strip()
    if not host or not endpoint:
        return ""

    namespace = os.getenv("CAIIS_NAMESPACE", CAIIS_DEFAULT_NAMESPACE).strip()
    if not namespace:
        namespace = CAIIS_DEFAULT_NAMESPACE

    api_path = _resolve_api_path("CAIIS_API_PATH", CAIIS_DEFAULT_API_PATH)
    return build_caiis_base_url(host, endpoint, namespace=namespace, api_path=api_path)


def resolve_llama_guard_base_url() -> str:
    """Prefer ``LLAMA_GUARD_BASE_URL``; else build from ``LLAMA_GUARD_HOST`` + endpoint."""
    explicit = os.getenv("LLAMA_GUARD_BASE_URL", "").strip()
    if explicit:
        return explicit

    host = os.getenv("LLAMA_GUARD_HOST", "").strip()
    if not host:
        host = os.getenv("CAIIS_HOST", "").strip()

    endpoint = os.getenv("LLAMA_GUARD_ENDPOINT", "").strip()
    if not endpoint:
        endpoint = LLAMA_GUARD_DEFAULT_ENDPOINT

    if not host:
        return ""

    namespace = os.getenv("LLAMA_GUARD_NAMESPACE", "").strip()
    if not namespace:
        namespace = os.getenv("CAIIS_NAMESPACE", CAIIS_DEFAULT_NAMESPACE).strip()
    if not namespace:
        namespace = CAIIS_DEFAULT_NAMESPACE

    api_path = _resolve_api_path("LLAMA_GUARD_API_PATH", CAIIS_DEFAULT_API_PATH)
    return build_caiis_base_url(host, endpoint, namespace=namespace, api_path=api_path)


def resolve_guardrails_server_url() -> str:
    """Prefer ``GUARDRAILS_SERVER_URL``; else ``https://{GUARDRAILS_HOST}``."""
    explicit = os.getenv("GUARDRAILS_SERVER_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    host = os.getenv("GUARDRAILS_HOST", "").strip()
    if not host:
        return ""

    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"https://{host}".rstrip("/")


def _url_is_configured(url: str, placeholders: tuple[str, ...]) -> bool:
    if not url:
        return False
    return not any(marker in url for marker in placeholders)


def is_caiis_url_configured(url: str | None = None) -> bool:
    """True when a resolved CAIIS base URL is set and not a placeholder."""
    resolved = url if url is not None else resolve_caiis_base_url()
    return _url_is_configured(resolved, CAIIS_PLACEHOLDER_MARKERS)


def is_llama_guard_url_configured(url: str | None = None) -> bool:
    """True when a resolved Llama Guard base URL is set and not a placeholder."""
    resolved = url if url is not None else resolve_llama_guard_base_url()
    return _url_is_configured(resolved, LLAMA_GUARD_PLACEHOLDER_MARKERS)
