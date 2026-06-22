#!/usr/bin/env bash
# Start NeMo Guardrails centralized server (session/CLI wrapper).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

exec python3 "${ROOT}/applications/guardrails_server_app.py" --mode session
