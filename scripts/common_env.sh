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
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-6.1-sol}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}"

# CAIIS: web UI defaults to OpenAI unless DEFAULT_LLM_PROVIDER=caiis (see detect_default_provider)
# CDP token: env var or CDSW session file (for CAIIS auth)
if [[ -z "${CDP_TOKEN:-}" ]] && [[ -f /tmp/jwt ]]; then
  export CDP_TOKEN="$(tr -d '[:space:]' < /tmp/jwt)"
fi

# CrewAI and NeMo read OPENAI_API_KEY; map CDP token when using CAIIS.
_caiis_configured=false
if [[ -n "${CAIIS_BASE_URL:-}" ]] || { [[ -n "${CAIIS_HOST:-}" ]] && [[ -n "${CAIIS_ENDPOINT:-}" ]]; }; then
  _caiis_configured=true
fi
if [[ "${_caiis_configured}" == true ]] && [[ -z "${OPENAI_API_KEY:-}" ]] && [[ -n "${CDP_TOKEN:-}" ]]; then
  export OPENAI_API_KEY="${CDP_TOKEN}"
fi

pick_guardrails_bind() {
  python3 -c "
import sys
sys.path.insert(0, '${ROOT}')
from src.runtime.startup import pick_bind
host, port = pick_bind('session', 'guardrails')
print(f'{host} {port}')
"
}

print_guardrails_urls() {
  local bind_host="$1"
  local port="$2"

  echo ""
  echo "=== Guardrails server bound to port ${port} (${bind_host}) ==="
  echo "NeMo Guardrails server listening on ${bind_host}:${port}"
  echo "  API URL: http://127.0.0.1:${port}/"
  echo "  Web UI settings (Guardrails Server URL): http://127.0.0.1:${port}"
  echo "  (http://localhost:${port} also works on the same machine)"
  echo ""
  echo "  Add to .env (match this port):"
  echo "    GUARDRAILS_PORT=${port}"
  echo "    GUARDRAILS_SERVER_URL=http://127.0.0.1:${port}"
  echo ""
}
