# Architecture Specification

## Overview

This document specifies the internal architecture of OpenCode (versions 1.18.x and related builds), its session state management, its integration with the OpenAI Responses API, and the structural mechanics of the in-place binary patch.

---

## 1. Runtime Packaging Architecture

OpenCode is distributed as a single-file executable built on top of the Bun runtime. The packaging layout follows the Bun standalone executable convention:

```
+-------------------------------------------------------------+
| ELF 64-bit Executable Header (aarch64 / x86_64)            |
+-------------------------------------------------------------+
| Native Bun Runtime Engine (JavaScriptCore + Native Libs)    |
+-------------------------------------------------------------+
| Virtual File System Container (bunfs)                       |
|   - Node.js compatibility shims                             |
|   - Bundled JavaScript application code                     |
|   - AI SDK modules (@ai-sdk/openai, @ai-sdk/provider, etc.) |
+-------------------------------------------------------------+
| bunfs Metadata & File Offset Trailer Table                  |
+-------------------------------------------------------------+
```

### Virtual File System Constraints
Because Bun computes exact byte offsets into the executable to locate bundled modules inside `bunfs`, modifying the file size or inserting bytes into compiled code invalidates the trailer offset table. This causes Bun to fail during initialization with corrupted module read errors. Consequently, any binary-level remediation must maintain strict byte-length invariance.

---

## 2. Conversation State Pipeline

OpenCode decouples conversation storage from in-memory runtime objects using an embedded SQLite database (`opencode.db`).

### Schema Hierarchy
```
project
  └── session
        ├── message (Turn metadata, role, status, cost, token counters)
        └── part    (Discrete payload elements: text, reasoning, tool-call, patch)
```

### Table Definitions

#### `message` Table
* `id` (`TEXT PRIMARY KEY`): Unique message identifier (e.g., `msg_0a4c07e9a001...`).
* `session_id` (`TEXT`): Foreign key referencing `session.id`.
* `time_created`, `time_updated` (`INTEGER`): Epoch millisecond timestamps.
* `data` (`TEXT`): Serialized JSON object containing execution mode, token statistics, parent pointers, and optional error state.

#### `part` Table
* `id` (`TEXT PRIMARY KEY`): Unique part identifier (e.g., `prt_0a4bd6d9a001...`).
* `message_id` (`TEXT`): Foreign key referencing `message.id`.
* `session_id` (`TEXT`): Foreign key referencing `session.id`.
* `data` (`TEXT`): Serialized JSON object representing individual content segments:
  * `text`: User prompts or assistant text completions.
  * `tool`: Tool invocations, execution inputs, and return states.
  * `patch`: File diffs and git modification snapshots.
  * `reasoning`: Chain-of-thought metadata blocks containing `providerMetadata`.

---

## 3. The Replay Engine and Upstream Failure Mechanics

When sending a turn to the LLM backend via the OpenAI Responses protocol (`/zen/v1/responses`), OpenCode traverses the session's historical parts to reconstruct the conversation tree.

```
[Session History in SQLite]
          |
          v
[Load Parts Array]
          |
          v
[Inspect Part Type]
          |
     +----+----+
     |         |
[type: "text"] [type: "reasoning"]
     |         |
     |         v
     |   Extract metadata.openai.reasoningEncryptedContent
     |         |
     |         +--> If present: push { type: "reasoning", encrypted_content: blob }
     |         +--> If absent : skip reasoning part
     v
[Assemble Final Request Payload]
          |
          v
[HTTPS POST to Gateway]
```

### Code Trace (Decompiled from Bun Bundle)

```javascript
let x = V == null ? void 0 : V.reasoningEncryptedContent;
if (x != null) {
  let T = [];
  if (w.text.length > 0) T.push({ type: "summary_text", text: w.text });
  N.push({ type: "reasoning", encrypted_content: x, summary: T });
} else {
  GQ.push({ type: "other", message: "Skipping reasoning parts." });
}

N = N.filter((a) => !("type" in a) || a.type !== "reasoning" || a.encrypted_content != null);
return { input: N, warnings: GQ };
```

### The Failure Trigger
1. When reasoning models generate thinking output, the backend returns an encrypted token representing the model's internal cache state.
2. OpenCode persists this token under `part.data.metadata.openai.reasoningEncryptedContent`.
3. In turn `N+1`, OpenCode reads `V.reasoningEncryptedContent` and constructs an outgoing request item containing `encrypted_content`.
4. Upstream providers bind this token cryptographically to a session caller context and assign it a strict time-to-live.
5. If the caller context changes or the TTL expires, the upstream gateway issues an HTTP 400 Bad Request:
   `[invalid_request_error] reasoning 'encrypted_content' was not issued to this caller`.

---

## 4. In-Place Binary Patch Mechanics

The remediation implemented by this repository alters the property lookup inside the compiled bundle without re-linking or modifying file offsets.

### Invariant Replacement

| Parameter | Original Sequence | Patched Sequence |
| :--- | :--- | :--- |
| ASCII Representation | `.reasoningEncryptedContent` | `.nonReplayEncryptedContent` |
| Byte Length | 26 bytes | 26 bytes |
| Evaluation on `V` | `"Q-PaDgGv..."` (truthy string) | `undefined` (falsy) |
| Conditional Branch | Enters `if (x != null)` | Enters `else` (omits token) |

### Runtime Execution Result
Because `V.nonReplayEncryptedContent` evaluates to `undefined`, `x` remains `undefined`. OpenCode skips emitting the `encrypted_content` object into the request payload. The conversation history is sent with full textual fidelity, prompt context, and tool invocations, but without the rejected token.
