#!/usr/bin/env bash
set -euo pipefail

echo "==========================================================="
echo " OpenCode Reasoning Encrypted Content Fixer"
echo " Fixes: [invalid_request_error] reasoning encrypted_content"
echo "==========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Terminate running OpenCode instances to prevent SQLite locks
echo "[*] Checking for running OpenCode processes..."
pkill -f "opencode.*web" 2>/dev/null || true
pkill -f "opencode-bin" 2>/dev/null || true
sleep 1

# 2. Patch binary
echo ""
echo "[*] Step 1: Applying binary patch..."
python3 "${SCRIPT_DIR}/patch_binary.py"

# 3. Sanitize database
echo ""
echo "[*] Step 2: Sanitizing SQLite database..."
python3 "${SCRIPT_DIR}/sanitize_db.py"

# 4. Verification
echo ""
echo "[*] Step 3: Verifying OpenCode CLI..."
if command -v opencode >/dev/null 2>&1; then
    OPENCODE_VER="$(opencode --version 2>/dev/null || echo 'Unknown')"
    echo "[✓] OpenCode installed version: ${OPENCODE_VER}"
    echo "[✓] Fix applied successfully! You can now resume your sessions."
else
    echo "[!] opencode command not found in PATH, but files were patched."
fi

echo "==========================================================="
