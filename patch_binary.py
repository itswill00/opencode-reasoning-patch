#!/usr/bin/env python3
"""
OpenCode Binary Patcher
Fixes: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller

Mechanics:
Replaces the 25-byte property access `.reasoningEncryptedContent` with
`.nonReplayEncryptedContent` in the compiled OpenCode ELF/Bun executable.
This prevents OpenCode from bundling expired encrypted reasoning tokens
into outgoing request payloads without shifting ELF offsets or file size.
"""

import sys
import os
import shutil

TARGET_SEARCH_PATHS = [
    "/data/data/com.termux/files/usr/libexec/opencode-bin",
    "/data/data/com.termux/files/usr/bin/opencode",
    os.path.expanduser("~/.local/bin/opencode"),
    "/usr/local/bin/opencode",
    "/usr/bin/opencode",
]

ORIG_PATTERN = b".reasoningEncryptedContent"
NEW_PATTERN  = b".nonReplayEncryptedContent"

assert len(ORIG_PATTERN) == len(NEW_PATTERN) == 26, f"Length mismatch: {len(ORIG_PATTERN)} vs {len(NEW_PATTERN)}"

def find_target(override_path=None):
    if override_path:
        if os.path.isfile(override_path):
            return override_path
        print(f"[!] Specified file not found: {override_path}")
        sys.exit(1)

    for p in TARGET_SEARCH_PATHS:
        if os.path.isfile(p):
            # Check if it's a wrapper shell script pointing to the actual binary
            with open(p, "rb") as f:
                head = f.read(256)
            if head.startswith(b"#!/"):
                for line in head.decode("latin1", "replace").splitlines():
                    for token in line.split():
                        if os.path.isfile(token) and "bin" in token and token != p:
                            return token
            return p

    print("[!] Could not auto-detect OpenCode binary. Provide path as argument.")
    sys.exit(1)

def patch_binary(target_path):
    print(f"[*] Inspecting target binary: {target_path}")

    with open(target_path, "rb") as f:
        data = f.read()

    orig_matches = data.count(ORIG_PATTERN)
    new_matches = data.count(NEW_PATTERN)

    print(f"[*] Found {orig_matches} instances of '{ORIG_PATTERN.decode()}'")
    print(f"[*] Found {new_matches} instances of '{NEW_PATTERN.decode()}'")

    if orig_matches == 0:
        if new_matches > 0:
            print("[✓] Binary is ALREADY patched! Nothing to do.")
            return True
        else:
            print("[!] Pattern not found in binary. Your OpenCode version might use a different structure or is already fixed upstream.")
            return False

    # Create backup if not exists
    backup_path = target_path + ".orig"
    if not os.path.exists(backup_path):
        print(f"[*] Creating backup at: {backup_path}")
        shutil.copy2(target_path, backup_path)
    else:
        print(f"[*] Backup already exists at: {backup_path}")

    patched_data = data.replace(ORIG_PATTERN, NEW_PATTERN)
    assert len(patched_data) == len(data), "File size changed during patch! Aborting."

    with open(target_path, "wb") as f:
        f.write(patched_data)

    os.chmod(target_path, 0o755)
    print(f"[✓] Successfully patched {orig_matches} occurrences in {target_path}!")
    return True

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    binary = find_target(target)
    success = patch_binary(binary)
    sys.exit(0 if success else 1)
