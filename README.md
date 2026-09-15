# OpenCode Reasoning Encrypted Content Remediation Engine

Technical specification, forensic analysis, in-place binary patcher, and SQLite database sanitizer resolving upstream reasoning token replay failures:

```text
AI_APICallError: Error from provider (Console): Upstream request failed: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller
```

---

## Executive Summary

Users interacting with reasoning models (such as `opencode/muse-spark-1.3-contributor-free`, DeepSeek thinking snapshots, or OpenAI reasoning derivatives) through OpenCode frequently encounter terminal session freezes. When a multi-turn conversation transitions across idle periods, mode changes, or tool executions, the upstream gateway rejects subsequent turns with an HTTP 400 Bad Request.

The failure stems from a defect in how OpenCode round-trips volatile encrypted reasoning tokens back to upstream inference proxies. This repository provides an automated, non-destructive, two-tier solution that:

1. Modifies property access inside compiled OpenCode standalone ELF executables in-place, permanently neutralizing the replay of expired reasoning tokens without altering binary offsets or invalidating Bun virtual filesystem headers.
2. Traverses and sanitizes existing conversation graphs inside local SQLite storage (`opencode.db`), unbricking locked sessions while preserving 100 percent of prompt history, textual thoughts, tool inputs, and workspace diffs.

---

## Repository Structure

```
opencode-reasoning-patch/
├── bin/
│   └── opencode-fix             Executable CLI wrapper
├── docs/
│   ├── ARCHITECTURE.md          Detailed packaging, runtime, and serialization analysis
│   ├── FORENSICS.md             Crash logs, HTTP response payloads, and database records
│   └── REPRODUCTION.md          Deterministic reproduction and verification protocol
├── scripts/
│   ├── patch_binary.py          In-place ELF binary patcher preserving byte alignment
│   └── sanitize_db.py           SQLite session sanitizer and unbricking utility
├── fix.sh                       Root automated orchestration script
├── LICENSE                      MIT License
└── README.md                    System documentation
```

---

## Technical Problem Analysis

### 1. Token Persistence Mechanics
When a reasoning model emits thinking output, the upstream inference gateway delivers an encrypted state token in the streaming response. OpenCode persists this token within its SQLite database (`opencode.db`) under the `part` table:

```json
{
  "type": "reasoning",
  "text": "",
  "metadata": {
    "openai": {
      "itemId": "rs_6aa926403b24a1ed...",
      "reasoningEncryptedContent": "Q-PaDgGv-a2T03W6aSU..."
    }
  }
}
```

### 2. Upstream Caller Rejection
On turn `N+1`, OpenCode's serializer iterates over historical parts to build the conversation array sent to `/zen/v1/responses`. When it encounters a reasoning part, it extracts `metadata.openai.reasoningEncryptedContent` and constructs an outgoing object with `encrypted_content`.

Because these encrypted blobs are cryptographically tied to a temporary caller session ticket, the upstream proxy rejects the replayed token once the caller context expires or resets:

```text
HTTP/2 400 Bad Request
Server: cloudflare
Content-Type: application/json

{
  "model": "muse-spark-1.3-contributor-free",
  "error": {
    "param": null,
    "type": "invalid_request_error",
    "message": "Error from provider (Console): Upstream request failed: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller"
  }
}
```

Because OpenCode marks the failed turn with an unhandled exception and persists the error into SQLite, the entire session remains permanently unusable.

---

## Solution Architecture

```
[OpenCode Client Execution]
            │
            ▼
┌───────────────────────────────────────┐
│ Layer 1: In-Place Binary Byte Patch   │
│ Scripts: scripts/patch_binary.py      │
└───────────────────┬───────────────────┘
                    │
                    ▼
     Property lookup altered to:
     .nonReplayEncryptedContent
                    │
                    ▼
     Evaluates to: undefined
                    │
                    ▼
     Condition 'if (x != null)' fails:
     Encrypted blob is omitted from request
                    │
                    ▼
     Upstream gateway accepts clean prompt

┌───────────────────────────────────────┐
│ Layer 2: SQLite Storage Sanitizer     │
│ Scripts: scripts/sanitize_db.py       │
└───────────────────┬───────────────────┘
                    │
                    ▼
     Traverses 'part' & 'message' tables:
     - Strips reasoningEncryptedContent
     - Clears HTTP 400 error status
                    │
                    ▼
     Existing broken sessions unbricked
```

### In-Place Binary Patching
OpenCode distributes single-file executables compiled with the Bun bundler. In this format, Bun embeds a virtual file system (`bunfs`) containing application code and runtime shims inside an ELF 64-bit executable. Altering the file size or shifting section offsets corrupts Bun's offset table, preventing the binary from executing.

To guarantee zero displacement:
* Original string: `.reasoningEncryptedContent` (26 bytes including the dot)
* Replacement string: `.nonReplayEncryptedContent` (26 bytes including the dot)

Because `nonReplayEncryptedContent` is never initialized on the runtime metadata object, lookups evaluate to `undefined`. The request serializer skips pushing `encrypted_content` into the outgoing request payload, sending a clean, standard conversation structure that the upstream gateway processes without error.

### Database State Sanitization
To restore access to existing projects that are already locked:
* `sanitize_db.py` parses `opencode.db` and recursively removes the `reasoningEncryptedContent` key from all entries in the `part` table.
* The script purges the error object from failed assistant nodes in the `message` table.
* A timestamped database backup is created automatically before any transaction is committed.

---

## Installation & Usage

### Prerequisites
* Python 3.8 or newer
* Bash shell environment (Linux x86_64, aarch64, or Android Termux)
* Standard POSIX utilities (`pkill`, `chmod`, `cp`)

### Automated Execution

Clone the repository and run the automated orchestrator:

```bash
git clone https://github.com/itswill00/opencode-reasoning-patch.git
cd opencode-reasoning-patch
chmod +x fix.sh bin/opencode-fix scripts/*.py
./fix.sh
```

The script will automatically:
1. Detect and terminate active OpenCode processes to release database locks.
2. Locate the OpenCode binary across standard distribution paths.
3. Apply the in-place 26-byte invariant patch (generating a `.orig` backup).
4. Sanitize `opencode.db` (generating a timestamped backup).
5. Verify OpenCode CLI responsiveness.

### Manual Invocation

#### 1. Terminate Running Instances
```bash
pkill -f "opencode.*web" || true
pkill -f "opencode-bin" || true
```

#### 2. Patch the Binary
```bash
python3 scripts/patch_binary.py /path/to/opencode-bin
```
*(On Termux environments, the binary resides at `/data/data/com.termux/files/usr/libexec/opencode-bin`)*

#### 3. Sanitize the SQLite Database
```bash
python3 scripts/sanitize_db.py ~/.local/share/opencode/opencode.db
```

#### 4. Resume OpenCode
```bash
opencode
# Or when running the web interface:
opencode web
```

---

## Command-Line Interface Reference

### `scripts/patch_binary.py`
```text
usage: patch_binary.py [-h] [--dry-run] [--no-backup] [binary_path]

positional arguments:
  binary_path   Path to the target executable (auto-detected if omitted).

options:
  -h, --help    Show this help message and exit.
  --dry-run     Simulate the patch process without writing to disk.
  --no-backup   Skip generating a .orig backup file before patching.
```

### `scripts/sanitize_db.py`
```text
usage: sanitize_db.py [-h] [--dry-run] [--no-backup] [db_path]

positional arguments:
  db_path       Path to opencode.db (auto-detected if omitted).

options:
  -h, --help    Show this help message and exit.
  --dry-run     Simulate database inspection and report counts without committing changes.
  --no-backup   Skip generating a timestamped database backup.
```

---

## Verification & Further Documentation

* For internal architecture diagrams and decompiled bundle references, see [Architecture Specification](docs/ARCHITECTURE.md).
* For detailed incident captures, HTTP header dumps, and raw database payloads, see [Forensic Log Analysis](docs/FORENSICS.md).
* For step-by-step reproduction and validation commands, see [Reproduction & Verification Guide](docs/REPRODUCTION.md).

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
