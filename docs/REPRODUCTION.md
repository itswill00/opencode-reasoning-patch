# Reproduction & Verification Guide

## 1. Prerequisites for Reproduction

The vulnerability exists in OpenCode runtime builds (versions <= 1.18.31) under the following conditions:

* **Model Family:** Any reasoning model hosted behind OpenCode's Zen/Console proxy that emits encrypted reasoning blobs (e.g., `opencode/muse-spark-1.3-contributor-free`).
* **Multi-Turn Interaction:** The session must execute at least one turn that receives reasoning metadata, followed by a state transition (session restart, idle timeout exceeding 15 minutes, or tool calling loops).

---

## 2. Deterministic Reproduction Sequence

### Step 1: Initialize New Session
Launch an OpenCode session targeting a reasoning model:
```bash
opencode run "List 3 optimization techniques for Python SQLite operations." -m opencode/muse-spark-1.3-contributor-free
```

### Step 2: Confirm Reasoning Part Persistence
Inspect the local SQLite database to confirm the encrypted token was recorded:
```bash
python3 -c "
import sqlite3
con = sqlite3.connect('$HOME/.local/share/opencode/opencode.db')
row = con.execute('SELECT id, substr(data, 1, 150) FROM part WHERE data LIKE \"%reasoningEncryptedContent%\" ORDER BY time_created DESC LIMIT 1').fetchone()
print('Stored token in part:', row)
"
```

### Step 3: Trigger Follow-up Turn After Delay
Allow the upstream caller session ticket to expire (either wait 15–20 minutes, or execute tool runs that force caller context renegotiation), then issue a second prompt in the same session:
```bash
opencode run "Summarize your previous response into 1 sentence." -c
```

### Observed Result
The process terminates with an unhandled exception:
```
AI_APICallError: Error from provider (Console): Upstream request failed: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller
```

---

## 3. Verification Protocol After Patch

### Step 1: Execute Remediation
Run the remediation suite:
```bash
./fix.sh
```

Expected output:
```text
----------------------------------------------------------------
OpenCode Reasoning Encrypted Content Remediation Engine
Target Error: [invalid_request_error] reasoning encrypted_content
----------------------------------------------------------------
[1/3] Terminating active OpenCode runtime instances...

[2/3] Executing in-place binary property modification...
Target Binary : /data/data/com.termux/files/usr/libexec/opencode-bin
File Size     : 184,526,992 bytes
Unpatched Occurrences : 0
Patched Occurrences   : 22
Status        : Binary has already been patched. No action required.

[3/3] Sanitizing SQLite conversation state...
Target Database : /data/data/com.termux/files/home/.local/share/opencode/opencode.db
Contaminated Parts Detected  : 0
Failed Session Messages Detected : 0
Status : Database is already clean. No contaminated records found.

----------------------------------------------------------------
Status: Remediation successful. OpenCode CLI version: 1.18.31
Active sessions have been unbricked and reasoning replay is disabled.
----------------------------------------------------------------
```

### Step 2: Test Resumption on Previously Failed Session
Resume the exact session ID that was previously throwing the 400 error:
```bash
opencode run "Acknowledge this message with the word SUCCESS." -c
```

### Expected Result
The model responds immediately without API errors:
```
> build · muse-spark-1.3-contributor-free

SUCCESS
```

### Step 3: Verify Clean Stream in Logs
Inspect recent log output in `~/.local/share/opencode/log/opencode.log`:
```bash
tail -n 25 ~/.local/share/opencode/log/opencode.log
```
Confirm that:
1. `level=INFO` logs indicate successful completion of `stream`.
2. No `AI_APICallError` entries appear for the current timestamp.
