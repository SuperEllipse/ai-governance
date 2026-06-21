#!/usr/bin/env bash
# Start full banking demo: optional guardrails server + Streamlit UI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

# shellcheck source=scripts/common_env.sh
source "${SCRIPT_DIR}/common_env.sh"
export_pythonpath

START_SERVER="${START_GUARDRAILS_SERVER:-false}"
GUARDRAILS_PORT="${GUARDRAILS_PORT:-8000}"

if [ "${START_SERVER}" = "true" ]; then
  echo "Starting guardrails server in background on port ${GUARDRAILS_PORT}..."
  GUARDRAILS_PORT="${GUARDRAILS_PORT}" bash scripts/start_guardrails_server.sh &
  sleep 3
fi

read -r BIND_HOST PORT < <(pick_streamlit_bind)

echo "PYTHONPATH=${PYTHONPATH}"
echo "Starting Streamlit demo..."
echo ""
echo "Recommended: run guardrails server in a separate terminal first:"
echo "  bash scripts/start_guardrails_server.sh"
echo "Then select 'Centralized Server' mode in the Streamlit sidebar (default)."
echo ""
print_streamlit_urls "${BIND_HOST}" "${PORT}"

exec streamlit run app/streamlit_app.py \
  --server.port "${PORT}" \
  --server.address "${BIND_HOST}" \
  --browser.gatherUsageStats false
