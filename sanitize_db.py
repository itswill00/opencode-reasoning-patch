#!/usr/bin/env python3
"""
OpenCode SQLite Session Sanitizer
Fixes: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller

Mechanics:
1. Scans `opencode.db` for reasoning parts containing expired `reasoningEncryptedContent`.
2. Recursively purges the encrypted reasoning blobs while keeping conversation history, tool calls, and text intact.
3. Unbricks locked sessions by removing API 400 error states from the message table.
"""

import sys
import os
import sqlite3
import json
import shutil
import time

DEFAULT_DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")

def clean_dict(obj):
    cleaned = False
    if isinstance(obj, dict):
        if "reasoningEncryptedContent" in obj:
            del obj["reasoningEncryptedContent"]
            cleaned = True
        for k, v in list(obj.items()):
            if clean_dict(v):
                cleaned = True
    elif isinstance(obj, list):
        for item in obj:
            if clean_dict(item):
                cleaned = True
    return cleaned

def sanitize_database(db_path):
    if not os.path.isfile(db_path):
        print(f"[!] Database file not found: {db_path}")
        return False

    print(f"[*] Opening database: {db_path}")

    # Backup before modifying
    backup_path = f"{db_path}.backup_{int(time.time())}"
    print(f"[*] Creating backup: {backup_path}")
    shutil.copy2(db_path, backup_path)

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # 1. Clean parts table
    print("[*] Scanning 'part' table...")
    part_rows = cur.execute('SELECT id, data FROM part WHERE data LIKE "%reasoningEncryptedContent%"').fetchall()
    print(f"[*] Found {len(part_rows)} parts with reasoningEncryptedContent")

    cleaned_parts = 0
    for pid, data_str in part_rows:
        try:
            data = json.loads(data_str)
            if clean_dict(data):
                cur.execute('UPDATE part SET data=? WHERE id=?', (json.dumps(data, separators=(',', ':')), pid))
                cleaned_parts += 1
        except Exception as e:
            print(f"[!] Error processing part {pid}: {e}")

    # 2. Clean error messages that lock sessions
    print("[*] Scanning 'message' table for locked sessions...")
    err_rows = cur.execute('SELECT id, data FROM message WHERE data LIKE "%encrypted_content%"').fetchall()
    print(f"[*] Found {len(err_rows)} error messages")

    cleaned_msgs = 0
    for mid, data_str in err_rows:
        try:
            data = json.loads(data_str)
            changed = False
            if "error" in data:
                del data["error"]
                changed = True
            if clean_dict(data):
                changed = True
            if changed:
                cur.execute('UPDATE message SET data=? WHERE id=?', (json.dumps(data, separators=(',', ':')), mid))
                cleaned_msgs += 1
        except Exception as e:
            print(f"[!] Error processing message {mid}: {e}")

    con.commit()
    con.close()

    print(f"[✓] Sanitization complete!")
    print(f"    - Cleaned parts   : {cleaned_parts}")
    print(f"    - Unbricked msgs  : {cleaned_msgs}")
    return True

if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    success = sanitize_database(db)
    sys.exit(0 if success else 1)
