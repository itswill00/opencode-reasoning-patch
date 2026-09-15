#!/usr/bin/env python3
"""
OpenCode SQLite Session Database Sanitizer

Purpose:
    Sanitizes existing OpenCode SQLite databases (`opencode.db`) affected by the
    expired reasoning encrypted token bug.

Mechanism:
    1. Scans the `part` table for JSON entries containing `"reasoningEncryptedContent"`.
    2. Recursively purges the `reasoningEncryptedContent` key from metadata payloads while
       leaving message text, thinking transcripts, tool invocations, and workspace diffs
       completely intact.
    3. Scans the `message` table for records frozen in an unrecoverable 400 Bad Request state
       caused by upstream provider rejection. Purges the error payload to unbrick the session.
    4. Creates a timestamped backup prior to applying transactions.
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time

DEFAULT_DB_LOCATIONS = [
    os.path.expanduser("~/.local/share/opencode/opencode.db"),
    os.path.expanduser("~/.config/opencode/opencode.db"),
]


def resolve_db_path(custom_path=None):
    if custom_path:
        path = os.path.abspath(os.path.expanduser(custom_path))
        if os.path.isfile(path):
            return path
        raise FileNotFoundError(f"Specified database file not found: {path}")

    for candidate in DEFAULT_DB_LOCATIONS:
        if os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError("Could not locate opencode.db in standard user data locations.")


def recursive_purge_key(node, key_name="reasoningEncryptedContent"):
    mutated = False
    if isinstance(node, dict):
        if key_name in node:
            del node[key_name]
            mutated = True
        for key in list(node.keys()):
            if recursive_purge_key(node[key], key_name):
                mutated = True
    elif isinstance(node, list):
        for item in node:
            if recursive_purge_key(item, key_name):
                mutated = True
    return mutated


def sanitize_database(db_path, dry_run=False, create_backup=True):
    db_path = os.path.realpath(db_path)
    print(f"Target Database : {db_path}")

    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database does not exist: {db_path}")

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    part_query = 'SELECT id, data FROM part WHERE data LIKE "%reasoningEncryptedContent%"'
    part_records = cur.execute(part_query).fetchall()

    err_query = 'SELECT id, session_id, data FROM message WHERE data LIKE "%encrypted_content%"'
    err_records = cur.execute(err_query).fetchall()

    print(f"Contaminated Parts Detected  : {len(part_records):,}")
    print(f"Failed Session Messages Detected : {len(err_records):,}")

    if len(part_records) == 0 and len(err_records) == 0:
        print("Status : Database is already clean. No contaminated records found.")
        con.close()
        return True

    if dry_run:
        print("Dry run enabled. No database records were modified.")
        con.close()
        return True

    con.close()

    if create_backup:
        backup_name = f"{db_path}.backup_{int(time.time())}"
        print(f"Creating database snapshot: {backup_name}")
        shutil.copy2(db_path, backup_name)

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cleaned_parts = 0
    for record_id, raw_json in part_records:
        try:
            payload = json.loads(raw_json)
            if recursive_purge_key(payload, "reasoningEncryptedContent"):
                updated_json = json.dumps(payload, separators=(",", ":"))
                cur.execute("UPDATE part SET data=? WHERE id=?", (updated_json, record_id))
                cleaned_parts += 1
        except Exception as exc:
            print(f"Warning: Failed to parse part {record_id}: {exc}", file=sys.stderr)

    unbricked_messages = 0
    for message_id, session_id, raw_json in err_records:
        try:
            payload = json.loads(raw_json)
            altered = False
            if "error" in payload:
                del payload["error"]
                altered = True
            if recursive_purge_key(payload, "reasoningEncryptedContent"):
                altered = True
            if altered:
                updated_json = json.dumps(payload, separators=(",", ":"))
                cur.execute("UPDATE message SET data=? WHERE id=?", (updated_json, message_id))
                unbricked_messages += 1
        except Exception as exc:
            print(f"Warning: Failed to parse message {message_id}: {exc}", file=sys.stderr)

    con.commit()
    con.close()

    print(f"Sanitization summary:")
    print(f"  - Parts cleansed         : {cleaned_parts:,}")
    print(f"  - Sessions unbricked     : {unbricked_messages:,}")
    print("Database state successfully synchronized and committed.")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Sanitize OpenCode SQLite session storage by stripping expired reasoning tokens."
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        default=None,
        help="Path to opencode.db (optional, auto-detected if omitted).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate database inspection and report counts without committing updates.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip generating a timestamped database backup before modification.",
    )

    args = parser.parse_args()

    try:
        target_db = resolve_db_path(args.db_path)
        success = sanitize_database(
            target_db,
            dry_run=args.dry_run,
            create_backup=not args.no_backup,
        )
        sys.exit(0 if success else 1)
    except Exception as exc:
        print(f"Execution failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
