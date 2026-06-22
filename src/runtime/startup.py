"""Environment, bind, and startup helpers for session scripts and CAI Applications."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Literal

Mode = Literal["session", "application"]
Service = Literal["streamlit", "guardrails"]


def _project_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


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
    os.environ.setdefault("OPENAI_MODEL", "gpt-4o-mini")
    os.environ.setdefault("OPENAI_BASE_URL", "https://api.openai.com/v1")
    os.environ.setdefault("MAIN_MODEL_ENGINE", "openai")

    if os.environ.get("CAIIS_BASE_URL"):
        os.environ.setdefault(
            "MAIN_MODEL_NAME",
            os.environ.get("CAIIS_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1"),
        )
        os.environ.setdefault("MAIN_MODEL_BASE_URL", os.environ["CAIIS_BASE_URL"])
    else:
        os.environ.setdefault("MAIN_MODEL_NAME", os.environ["OPENAI_MODEL"])
        os.environ.setdefault("MAIN_MODEL_BASE_URL", os.environ["OPENAI_BASE_URL"])

    if not os.environ.get("CDP_TOKEN"):
        token = _read_cdp_token_from_jwt()
        if token:
            os.environ["CDP_TOKEN"] = token

    if os.environ.get("CAIIS_BASE_URL") and not os.environ.get("OPENAI_API_KEY"):
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


def _application_bind_port() -> int:
    for key in ("CDSW_APP_PORT", "CDSW_READONLY_PORT"):
        port = _parse_port_env(key)
        if port is not None:
            return port
    raise RuntimeError(
        "Application mode requires CDSW_APP_PORT (or CDSW_READONLY_PORT) to be set."
    )


def pick_bind(mode: Mode, service: Service) -> tuple[str, int]:
    """Return ``(host, port)`` for Streamlit or the guardrails server."""
    if mode == "application":
        return "0.0.0.0", _application_bind_port()

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
            print("  Cloudera AI Application: use the public HTTPS URL for this app.")
            print("  Set GUARDRAILS_SERVER_URL on the Streamlit application to that URL.")
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
        print("  Cloudera AI Application: open the public HTTPS URL for this app.")
        print("  Ensure GUARDRAILS_SERVER_URL points at the guardrails application URL.")
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
