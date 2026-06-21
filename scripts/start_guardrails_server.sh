#!/usr/bin/env bash
# Start NeMo Guardrails centralized server (auto-bind 127.0.0.1; port 8000 or 8001 on CDSW)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

# shellcheck source=scripts/common_env.sh
source "${SCRIPT_DIR}/common_env.sh"
export_pythonpath

export MAIN_MODEL_ENGINE="${MAIN_MODEL_ENGINE:-openai}"

# Default to OpenAI; switch to CAIIS by setting CAIIS_BASE_URL / CAIIS_MODEL in .env
if [[ -n "${CAIIS_BASE_URL:-}" ]]; then
  export MAIN_MODEL_NAME="${MAIN_MODEL_NAME:-${CAIIS_MODEL:-nvidia/llama-3.3-nemotron-super-49b-v1}}"
  export MAIN_MODEL_BASE_URL="${MAIN_MODEL_BASE_URL:-${CAIIS_BASE_URL}}"
else
  export MAIN_MODEL_NAME="${MAIN_MODEL_NAME:-${OPENAI_MODEL:-gpt-4o-mini}}"
  export MAIN_MODEL_BASE_URL="${MAIN_MODEL_BASE_URL:-${OPENAI_BASE_URL:-https://api.openai.com/v1}}"
fi

# API key: OpenAI key first, then CDP token for CAIIS
if [[ -z "${OPENAI_API_KEY:-}" ]] && [[ -n "${CDP_TOKEN:-}" ]]; then
  export OPENAI_API_KEY="${CDP_TOKEN}"
elif [[ -z "${OPENAI_API_KEY:-}" ]] && [[ -f /tmp/jwt ]]; then
  export OPENAI_API_KEY="$(tr -d '[:space:]' < /tmp/jwt)"
fi
export OPENAI_API_KEY="${OPENAI_API_KEY:-}"

CONFIG_PATH="${GUARDRAILS_CONFIG:-./guardrails/base}"

read -r BIND_HOST PORT < <(pick_guardrails_bind)
export GUARDRAILS_HOST="${BIND_HOST}"
export GUARDRAILS_PORT="${PORT}"

echo "Starting NeMo Guardrails server..."
echo "  Config: $CONFIG_PATH"
echo "  Bind:   ${BIND_HOST}:${PORT}"
echo "  Model:  $MAIN_MODEL_NAME"
echo "  Base:   $MAIN_MODEL_BASE_URL"
echo "  PYTHONPATH=${PYTHONPATH}"
print_guardrails_urls "${BIND_HOST}" "${PORT}"

exec python3 "${SCRIPT_DIR}/run_guardrails_uvicorn.py" \
  --config "$CONFIG_PATH" \
  --host "${BIND_HOST}" \
  --port "${PORT}" \
  --default-config-id "banking_demo"
