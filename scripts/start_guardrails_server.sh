#!/usr/bin/env bash
# Start NVIDIA NeMo Guardrails centralized server on port 8000
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

# shellcheck source=scripts/common_env.sh
source "${SCRIPT_DIR}/common_env.sh"
export_pythonpath

export MAIN_MODEL_ENGINE="${MAIN_MODEL_ENGINE:-openai}"

# Default to OpenAI for testing; switch to CAIIS by setting CAIIS_BASE_URL / CAIIS_MODEL in .env
if [[ -n "${CAIIS_BASE_URL:-}" ]]; then
  export MAIN_MODEL_NAME="${MAIN_MODEL_NAME:-${CAIIS_MODEL:-nvidia/llama-3.3-nemotron-super-49b-v1}}"
  export MAIN_MODEL_BASE_URL="${MAIN_MODEL_BASE_URL:-${CAIIS_BASE_URL}}"
else
  export MAIN_MODEL_NAME="${MAIN_MODEL_NAME:-${OPENAI_MODEL:-gpt-4o-mini}}"
  export MAIN_MODEL_BASE_URL="${MAIN_MODEL_BASE_URL:-${OPENAI_BASE_URL:-https://api.openai.com/v1}}"
fi

# API key: OpenAI key first, then CDP token for CAIIS workbench sessions
if [[ -z "${OPENAI_API_KEY:-}" ]] && [[ -n "${CDP_TOKEN:-}" ]]; then
  export OPENAI_API_KEY="${CDP_TOKEN}"
elif [[ -z "${OPENAI_API_KEY:-}" ]] && [[ -f /tmp/jwt ]]; then
  export OPENAI_API_KEY="$(tr -d '[:space:]' < /tmp/jwt)"
fi
export OPENAI_API_KEY="${OPENAI_API_KEY:-}"

PORT="${GUARDRAILS_PORT:-8000}"
CONFIG_PATH="${GUARDRAILS_CONFIG:-./guardrails/base}"

echo "Starting NeMo Guardrails server..."
echo "  Config: $CONFIG_PATH"
echo "  Port:   $PORT"
echo "  Model:  $MAIN_MODEL_NAME"
echo "  Base:   $MAIN_MODEL_BASE_URL"
echo "  PYTHONPATH=${PYTHONPATH}"

exec nemoguardrails server \
  --config "$CONFIG_PATH" \
  --port "$PORT" \
  --default-config-id "banking_demo"
