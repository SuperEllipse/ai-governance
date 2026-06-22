#!/usr/bin/env bash
# Start Streamlit banking demo (session/CLI wrapper).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

START_SERVER="${START_GUARDRAILS_SERVER:-false}"
GUARDRAILS_PORT="${GUARDRAILS_PORT:-8001}"

if [ "${START_SERVER}" = "true" ]; then
  echo "Starting guardrails server in background (preferred port ${GUARDRAILS_PORT}; see script output for actual bind)..."
  GUARDRAILS_PORT="${GUARDRAILS_PORT}" bash scripts/start_guardrails_server.sh &
  sleep 3
fi

exec python3 "${ROOT}/applications/streamlit_demo_app.py" --mode session
