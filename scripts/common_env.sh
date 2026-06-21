#!/usr/bin/env bash
# Shared environment for NeMo Banking Demo start scripts.

# ROOT must be set by the caller (project root directory).
: "${ROOT:?ROOT must be set before sourcing common_env.sh}"

export_pythonpath() {
  if [[ ":${PYTHONPATH:-}:" != *":${ROOT}:"* ]]; then
    export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
  fi
}

# Load .env if present (never commit .env — use .env.example templates)
load_env_file() {
  local env_file="$1"
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
  fi
}

_sourced_env=""
if [[ -f "${ROOT}/.env" ]]; then
  load_env_file "${ROOT}/.env"
  _sourced_env="$(readlink -f "${ROOT}/.env" 2>/dev/null || echo "${ROOT}/.env")"
fi
if [[ -f "/home/cdsw/.env" ]]; then
  _cdsw_env="$(readlink -f "/home/cdsw/.env" 2>/dev/null || echo "/home/cdsw/.env")"
  if [[ "${_sourced_env}" != "${_cdsw_env}" ]]; then
    load_env_file "/home/cdsw/.env"
  fi
fi

# OpenAI defaults when using the OpenAI provider (override via .env or export)
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}"

# CAIIS: auto-select in Streamlit when CAIIS_BASE_URL is set (see detect_default_provider)
# CDP token: env var or CDSW session file (for CAIIS auth)
if [[ -z "${CDP_TOKEN:-}" ]] && [[ -f /tmp/jwt ]]; then
  export CDP_TOKEN="$(tr -d '[:space:]' < /tmp/jwt)"
fi

# CrewAI and NeMo read OPENAI_API_KEY; map CDP token when using CAIIS.
if [[ -n "${CAIIS_BASE_URL:-}" ]] && [[ -z "${OPENAI_API_KEY:-}" ]] && [[ -n "${CDP_TOKEN:-}" ]]; then
  export OPENAI_API_KEY="${CDP_TOKEN}"
fi

pick_streamlit_bind() {
  python3 - <<'PY'
import os
import socket
import sys


def can_bind(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


candidates: list[int] = []
for key in ("STREAMLIT_PORT", "CDSW_APP_PORT"):
    raw = os.environ.get(key)
    if raw:
        try:
            candidates.append(int(raw))
        except ValueError:
            print(f"Invalid {key}={raw!r}", file=sys.stderr)

for fallback in (8501, 8090, 8080):
    if fallback not in candidates:
        candidates.append(fallback)

hosts = ("127.0.0.1", "0.0.0.0")

for port in candidates:
    for host in hosts:
        if can_bind(host, port):
            print(f"{host} {port}")
            sys.exit(0)

print("Could not find an available host/port for Streamlit.", file=sys.stderr)
sys.exit(1)
PY
}

pick_guardrails_bind() {
  python3 - <<'PY'
import os
import socket
import sys


def can_bind(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


candidates: list[int] = []
raw = os.environ.get("GUARDRAILS_PORT")
if raw:
    try:
        candidates.append(int(raw))
    except ValueError:
        print(f"Invalid GUARDRAILS_PORT={raw!r}", file=sys.stderr)

for fallback in (8000, 8001, 8080):
    if fallback not in candidates:
        candidates.append(fallback)

# Prefer loopback — CDSW often holds 8000 on 0.0.0.0 (pod IP) for the app proxy.
hosts = ("127.0.0.1", "0.0.0.0")

for port in candidates:
    for host in hosts:
        if can_bind(host, port):
            print(f"{host} {port}")
            sys.exit(0)

print("Could not find an available host/port for the guardrails server.", file=sys.stderr)
sys.exit(1)
PY
}

print_streamlit_urls() {
  local bind_host="$1"
  local port="$2"

  echo ""
  echo "Streamlit binding: ${bind_host}:${port}"
  echo "  Direct URL: http://127.0.0.1:${port}/"

  if [ -n "${CDSW_APP_PORT:-}" ] && [ "${port}" = "${CDSW_APP_PORT}" ] && [ "${bind_host}" = "127.0.0.1" ]; then
    echo "  CDSW: use the session Application on port ${CDSW_APP_PORT} (proxy to 127.0.0.1:${CDSW_APP_PORT})."
  fi

  if [ -n "${CDSW_DOMAIN:-}" ] && [ -n "${CDSW_MASTER_ID:-}" ] && [ -n "${CDSW_PROJECT:-}" ]; then
    local owner
    owner="$(echo "${CDSW_PROJECT_URL:-}" | sed -n 's|.*/projects/\([^/]*\)/.*|\1|p')"
    if [ -n "${owner}" ]; then
      echo "  Session: https://${CDSW_DOMAIN}/${owner}/${CDSW_PROJECT}/engine/${CDSW_MASTER_ID}/"
    fi
  fi
  echo ""
}

print_guardrails_urls() {
  local bind_host="$1"
  local port="$2"

  echo ""
  echo "NeMo Guardrails server listening on ${bind_host}:${port}"
  echo "  API URL: http://127.0.0.1:${port}/"
  echo "  Streamlit sidebar (Centralized Server): http://127.0.0.1:${port}"
  echo "  (http://localhost:${port} also works on the same machine)"
  echo ""
}
