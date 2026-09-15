#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "----------------------------------------------------------------"
echo "OpenCode Reasoning Encrypted Content Remediation Engine"
echo "Target Error: [invalid_request_error] reasoning encrypted_content"
echo "----------------------------------------------------------------"

# Step 1: Check and terminate running processes holding database locks
echo "[1/3] Terminating active OpenCode runtime instances..."
pkill -f "opencode.*web" 2>/dev/null || true
pkill -f "opencode-bin" 2>/dev/null || true
sleep 1

# Step 2: Binary patch execution
echo ""
echo "[2/3] Executing in-place binary property modification..."
if [ -f "${SCRIPT_DIR}/scripts/patch_binary.py" ]; then
    python3 "${SCRIPT_DIR}/scripts/patch_binary.py" "$@"
elif [ -f "${SCRIPT_DIR}/patch_binary.py" ]; then
    python3 "${SCRIPT_DIR}/patch_binary.py" "$@"
else
    echo "Error: patch_binary.py script not found." >&2
    exit 1
fi

# Step 3: SQLite storage sanitization
echo ""
echo "[3/3] Sanitizing SQLite conversation state..."
if [ -f "${SCRIPT_DIR}/scripts/sanitize_db.py" ]; then
    python3 "${SCRIPT_DIR}/scripts/sanitize_db.py" "$@"
elif [ -f "${SCRIPT_DIR}/sanitize_db.py" ]; then
    python3 "${SCRIPT_DIR}/sanitize_db.py" "$@"
else
    echo "Error: sanitize_db.py script not found." >&2
    exit 1
fi

# Final status verification
echo ""
echo "----------------------------------------------------------------"
if command -v opencode >/dev/null 2>&1; then
    VER="$(opencode --version 2>/dev/null || echo 'Detected')"
    echo "Status: Remediation successful. OpenCode CLI version: ${VER}"
    echo "Active sessions have been unbricked and reasoning replay is disabled."
else
    echo "Status: Remediation completed. Files modified in-place."
fi
echo "----------------------------------------------------------------"
