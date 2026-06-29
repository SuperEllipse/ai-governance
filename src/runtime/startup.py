"""Environment, bind, and startup helpers for session scripts and CAI Applications."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Literal

Mode = Literal["session", "application"]
Service = Literal["streamlit", "guardrails"]

_CAI_PORT_KEYS = ("CDSW_APP_PORT", "CDSW_READONLY_PORT", "CDSW_PUBLIC_PORT")
_CAI_BIND_PORT_KEY_ENV = "CAI_BIND_PORT_KEY"


def _looks_like_project_root(path: Path) -> bool:
    return (path / "guardrails").is_dir() and (path / "applications").is_dir()


def resolve_project_root(anchor: str | None = None) -> Path:
    """Resolve project root with fallbacks for IPython/Jupyter where ``__file__`` is undefined."""
    if anchor:
        anchor_path = Path(anchor).resolve()
        candidate = anchor_path.parents[1]
        if _looks_like_project_root(candidate):
            return candidate
        for parent in anchor_path.parents:
            if _looks_like_project_root(parent):
                return parent

    cwd = Path.cwd()
    if _looks_like_project_root(cwd):
        return cwd.resolve()

    cdsw_home = Path("/home/cdsw")
    if _looks_like_project_root(cdsw_home):
        return cdsw_home.resolve()

    for env_key in ("CDSW_PROJECT_DIR", "PROJECT_ROOT", "PWD", "HOME"):
        raw = os.environ.get(env_key)
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if _looks_like_project_root(candidate):
            return candidate.resolve()

    if anchor:
        return Path(anchor).resolve().parents[1]

    return cwd.resolve()


def _project_root_from_here() -> Path:
    try:
        return resolve_project_root(__file__)
    except NameError:
        return resolve_project_root()


def load_dotenv_files(project_root: Path | None = None) -> None:
    """Load ``.env`` from the project root and ``/home/cdsw/.env`` when present."""
    root = project_root or _project_root_from_here()
    sourced: Path | None = None

    for env_file in (root / ".env", Path("/home/cdsw/.env")):
        if not env_file.is_file():
            continue
        resolved = env_file.resolve()
        if sourced is not None and resolved == sourced:
            continue
        _load_env_file(resolved)
        sourced = resolved


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def setup_pythonpath(project_root: Path | None = None) -> Path:
    """Ensure ``project_root`` is on ``sys.path`` and ``PYTHONPATH``."""
    root = (project_root or _project_root_from_here()).resolve()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    existing = os.environ.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if root_str not in parts:
        os.environ["PYTHONPATH"] = root_str + (f"{os.pathsep}{existing}" if existing else "")
    return root


def _read_cdp_token_from_jwt() -> str | None:
    jwt_path = Path("/tmp/jwt")
    if not jwt_path.is_file():
        return None
    return "".join(jwt_path.read_text(encoding="utf-8").split())


def configure_guardrails_llm_env() -> None:
    """Set MAIN_MODEL_* and OPENAI_API_KEY for the NeMo guardrails server."""
    from src.llm.caiis_url import resolve_caiis_base_url, resolve_caiis_model
    from src.llm.provider import is_caiis_configured

    os.environ.setdefault("OPENAI_MODEL", "gpt-4o-mini")
    os.environ.setdefault("OPENAI_BASE_URL", "https://api.openai.com/v1")
    os.environ.setdefault("MAIN_MODEL_ENGINE", "openai")

    caiis_url = resolve_caiis_base_url()
    if caiis_url and is_caiis_configured():
        os.environ.setdefault("MAIN_MODEL_NAME", resolve_caiis_model())
        os.environ.setdefault("MAIN_MODEL_BASE_URL", caiis_url)
    else:
        os.environ.setdefault("MAIN_MODEL_NAME", os.environ["OPENAI_MODEL"])
        os.environ.setdefault("MAIN_MODEL_BASE_URL", os.environ["OPENAI_BASE_URL"])

    if not os.environ.get("CDP_TOKEN"):
        token = _read_cdp_token_from_jwt()
        if token:
            os.environ["CDP_TOKEN"] = token

    if caiis_url and is_caiis_configured() and not os.environ.get("OPENAI_API_KEY"):
        if os.environ.get("CDP_TOKEN"):
            os.environ["OPENAI_API_KEY"] = os.environ["CDP_TOKEN"]

    if not os.environ.get("OPENAI_API_KEY"):
        token = os.environ.get("CDP_TOKEN") or _read_cdp_token_from_jwt()
        if token:
            os.environ["OPENAI_API_KEY"] = token

    os.environ.setdefault("OPENAI_API_KEY", "")
    os.environ.setdefault("DEFAULT_CONFIG_ID", "base")
    os.environ.setdefault("GUARDRAILS_CONFIG_ID", "base")


def _can_bind(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _parse_port_env(key: str) -> int | None:
    raw = os.environ.get(key)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        print(f"Invalid {key}={raw!r}", file=sys.stderr)
        return None


def _application_bind_port(service: Service) -> tuple[int, str]:
    """Return ``(port, env_key)`` for Cloudera AI Application mode."""
    if service == "streamlit":
        port = _parse_port_env("CDSW_APP_PORT")
        if port is not None:
            return port, "CDSW_APP_PORT"
        raise RuntimeError(
            "Streamlit in Cloudera AI Application mode requires CDSW_APP_PORT "
            "to be injected by the platform. Do not hardcode port numbers; "
            "register Streamlit as its own Application so the platform assigns a port."
        )

    bind_key = os.environ.get(_CAI_BIND_PORT_KEY_ENV, "").strip()
    if bind_key:
        if bind_key not in _CAI_PORT_KEYS:
            raise RuntimeError(
                f"Invalid {_CAI_BIND_PORT_KEY_ENV}={bind_key!r}. "
                f"Must be one of: {', '.join(_CAI_PORT_KEYS)}."
            )
        port = _parse_port_env(bind_key)
        if port is None:
            raise RuntimeError(
                f"{_CAI_BIND_PORT_KEY_ENV}={bind_key!r} but {bind_key} is not set."
            )
        return port, bind_key

    for key in _CAI_PORT_KEYS:
        port = _parse_port_env(key)
        if port is not None:
            return port, key

    raise RuntimeError(
        "Guardrails server in Cloudera AI Application mode requires at least one of "
        f"{', '.join(_CAI_PORT_KEYS)} to be injected by the platform."
    )


def _pick_application_bind(service: Service) -> tuple[str, int]:
    """Bind the platform port on localhost only (per Cloudera CDSW docs)."""
    port, port_key = _application_bind_port(service)
    label = "Streamlit" if service == "streamlit" else "guardrails server"
    host = "127.0.0.1"
    if not _can_bind(host, port):
        raise RuntimeError(
            f"Could not bind {label} to {host}:{port} ({port_key}). "
            "Only one web app may bind each platform port per engine; "
            "see Cloudera docs on port availability."
        )
    return host, port


def pick_bind(mode: Mode, service: Service) -> tuple[str, int]:
    """Return ``(host, port)`` for Streamlit or the guardrails server."""
    if mode == "application":
        return _pick_application_bind(service)

    if service == "streamlit":
        candidates: list[int] = []
        for key in ("STREAMLIT_PORT", "CDSW_APP_PORT"):
            port = _parse_port_env(key)
            if port is not None:
                candidates.append(port)
        for fallback in (8501, 8090, 8080):
            if fallback not in candidates:
                candidates.append(fallback)
        hosts = ("127.0.0.1", "0.0.0.0")
    else:
        candidates = []
        port = _parse_port_env("GUARDRAILS_PORT")
        if port is not None:
            candidates.append(port)
        for fallback in (8000, 8001, 8080):
            if fallback not in candidates:
                candidates.append(fallback)
        hosts = ("127.0.0.1", "0.0.0.0")

    for port in candidates:
        for host in hosts:
            if _can_bind(host, port):
                return host, port

    label = "Streamlit" if service == "streamlit" else "guardrails server"
    raise RuntimeError(f"Could not find an available host/port for {label}.")


def get_guardrails_config_path(project_root: Path | None = None) -> Path:
    """Resolve the guardrails config directory (parent of policy modules)."""
    root = (project_root or _project_root_from_here()).resolve()
    raw = os.environ.get("GUARDRAILS_CONFIG", str(root / "guardrails"))
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    else:
        path = path.resolve()
    return path


def _application_port_key(service: Service, port: int) -> str:
    """Resolve which platform env var selected the bind port."""
    if service == "streamlit":
        return "CDSW_APP_PORT"

    bind_key = os.environ.get(_CAI_BIND_PORT_KEY_ENV, "").strip()
    if bind_key in _CAI_PORT_KEYS:
        return bind_key

    for key in _CAI_PORT_KEYS:
        raw = os.environ.get(key)
        if raw and str(port) == raw.strip():
            return key
    return "CDSW_APP_PORT"


def _cdsw_public_url_pattern(port_key: str) -> str:
    patterns = {
        "CDSW_APP_PORT": "https://<$CDSW_ENGINE_ID>.<$CDSW_DOMAIN>",
        "CDSW_READONLY_PORT": "https://read-only-<$CDSW_ENGINE_ID>.<$CDSW_DOMAIN>",
        "CDSW_PUBLIC_PORT": "https://public-<$CDSW_ENGINE_ID>.<$CDSW_DOMAIN>",
    }
    return patterns.get(port_key, f"({port_key})")


def _cdsw_public_url_resolved(port_key: str) -> str | None:
    engine_id = os.environ.get("CDSW_ENGINE_ID")
    domain = os.environ.get("CDSW_DOMAIN")
    if not engine_id or not domain:
        return None
    if port_key == "CDSW_APP_PORT":
        return f"https://{engine_id}.{domain}"
    if port_key == "CDSW_READONLY_PORT":
        return f"https://read-only-{engine_id}.{domain}"
    if port_key == "CDSW_PUBLIC_PORT":
        return f"https://public-{engine_id}.{domain}"
    return None


def _application_port_env_line(service: Service, port: int) -> str:
    """Explain which platform env var selected the bind port in application mode."""
    port_key = _application_port_key(service, port)
    suffix = (
        "(platform-injected; GUARDRAILS_PORT is ignored in application mode)"
    )
    return f"Using {port_key}={port} {suffix}"


def _cdsw_loopback_proxy_line(service: Service, bind_host: str, port: int) -> str | None:
    """Note when loopback bind relies on the CDSW application proxy."""
    if bind_host != "127.0.0.1":
        return None
    port_key = _application_port_key(service, port)
    return (
        f"  CDSW proxy: bound to 127.0.0.1:{port} (localhost per Cloudera docs); "
        f"public traffic on {port_key} is forwarded to this loopback port."
    )


def _cdsw_public_url_line(service: Service, port: int) -> str:
    port_key = _application_port_key(service, port)
    resolved = _cdsw_public_url_resolved(port_key)
    pattern = _cdsw_public_url_pattern(port_key)
    if resolved:
        return f"  Session public URL ({port_key}): {resolved}"
    return f"  Session public URL ({port_key}): {pattern}"


def print_startup_banner(
    service: Service,
    *,
    bind_host: str,
    port: int,
    mode: Mode,
    extra_lines: list[str] | None = None,
) -> None:
    """Print human-readable startup URLs and hints."""
    extra_lines = extra_lines or []

    if service == "guardrails":
        print("")
        print(f"=== Guardrails server bound to port {port} ({bind_host}) ===")
        print(f"NeMo Guardrails server listening on {bind_host}:{port}")
        print(f"  API URL: http://127.0.0.1:{port}/")
        print(f"  Streamlit sidebar (Centralized Server): http://127.0.0.1:{port}")
        print(f"  (http://localhost:{port} also works on the same machine)")
        print("")
        if mode == "application":
            print(f"  {_application_port_env_line(service, port)}")
            proxy_line = _cdsw_loopback_proxy_line(service, bind_host, port)
            if proxy_line:
                print(proxy_line)
            print(_cdsw_public_url_line(service, port))
            print(
                "  CAI Application public URL: https://<subdomain>.<YOUR-CAI-DOMAIN> "
                "(set subdomain in the Application UI)."
            )
            print("  GUARDRAILS_PORT only applies to session/bash mode (start_guardrails_server.sh).")
            print(
                "  On Application 2 (Streamlit), set GUARDRAILS_SERVER_URL to Application 1's "
                "public HTTPS URL — not http://127.0.0.1 or localhost."
            )
        else:
            print("  Add to .env (match this port):")
            print(f"    GUARDRAILS_PORT={port}")
            print(f"    GUARDRAILS_SERVER_URL=http://127.0.0.1:{port}")
        for line in extra_lines:
            print(line)
        print("")
        return

    print("")
    print(f"Streamlit binding: {bind_host}:{port}")
    print(f"  Direct URL: http://127.0.0.1:{port}/")

    if (
        mode == "session"
        and os.environ.get("CDSW_APP_PORT")
        and str(port) == os.environ["CDSW_APP_PORT"]
        and bind_host == "127.0.0.1"
    ):
        print(
            f"  CDSW: use the session Application on port {os.environ['CDSW_APP_PORT']} "
            f"(proxy to 127.0.0.1:{os.environ['CDSW_APP_PORT']})."
        )

    if mode == "application":
        print(f"  {_application_port_env_line(service, port)}")
        proxy_line = _cdsw_loopback_proxy_line(service, bind_host, port)
        if proxy_line:
            print(proxy_line)
        print(_cdsw_public_url_line(service, port))
        print(
            "  CAI Application public URL: https://<subdomain>.<YOUR-CAI-DOMAIN> "
            "(e.g. https://banking-demo.YOUR-CAI-DOMAIN)."
        )
        print("  GUARDRAILS_PORT only applies to session/bash mode.")
        print(
            "  Set GUARDRAILS_SERVER_URL to Application 1's public HTTPS URL "
            "(e.g. https://nemo-guardrails.YOUR-CAI-DOMAIN), not localhost."
        )
    elif os.environ.get("CDSW_DOMAIN") and os.environ.get("CDSW_MASTER_ID"):
        owner = ""
        project_url = os.environ.get("CDSW_PROJECT_URL", "")
        if "/projects/" in project_url:
            owner = project_url.split("/projects/", 1)[1].split("/", 1)[0]
        project = os.environ.get("CDSW_PROJECT", "")
        if owner and project:
            print(
                f"  Session: https://{os.environ['CDSW_DOMAIN']}/{owner}/{project}/"
                f"engine/{os.environ['CDSW_MASTER_ID']}/"
            )

    for line in extra_lines:
        print(line)
    print("")
