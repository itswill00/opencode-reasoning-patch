# Forensic Investigation & Incident Log Analysis

## 1. Incident Description

During prolonged interactive coding workflows on OpenCode (version 1.18.31), sessions entering turn `N+1` after background file edits or idle pauses consistently fail with an upstream API rejection:

```
AI_APICallError: Error from provider (Console): Upstream request failed: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller
```

---

## 2. Server Log Capture

The following log trace was captured directly from `~/.local/share/opencode/log/opencode.log` during an active reproduction:

```log
timestamp=2026-09-15T11:07:54.968Z level=INFO run=ff6aa420 message=stream providerID=opencode modelID=muse-spark-1.3-contributor-free session.id=ses_f5b51c6cbffesIufhP8OXV6pzc small=false agent=build mode=primary
timestamp=2026-09-15T11:07:55.096Z level=INFO run=ff6aa420 message="llm runtime selected" llm.runtime=ai-sdk llm.provider=opencode llm.model=muse-spark-1.3-contributor-free
timestamp=2026-09-15T11:07:57.391Z level=ERROR run=ff6aa420 message="stream error" providerID=opencode modelID=muse-spark-1.3-contributor-free session.id=ses_f5b51c6cbffesIufhP8OXV6pzc small=false agent=build mode=primary error.error="AI_APICallError: Error from provider (Console): Upstream request failed: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller"
timestamp=2026-09-15T11:07:57.398Z level=ERROR run=ff6aa420 message=process session.id=ses_f5b51c6cbffesIufhP8OXV6pzc messageID=msg_0a4c07e9a001Whc2jKaUSpKPop error="Error from provider (Console): Upstream request failed: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller" stack="AI_APICallError: Error from provider (Console): Upstream request failed: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller\n    at <anonymous> (/$bunfs/root/chunk-pbrky899.js:7:14723)\n    at async <anonymous> (/$bunfs/root/chunk-pbrky899.js:7:12930)\n    at processTicksAndRejections (native:7:39)"
```

---

## 3. Upstream HTTP Response Analysis

When examining the serialized error payload stored in the `message` database table:

```json
{
  "name": "APIError",
  "data": {
    "message": "Error from provider (Console): Upstream request failed: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller",
    "statusCode": 400,
    "isRetryable": false,
    "responseHeaders": {
      "cf-placement": "remote-ORD",
      "cf-ray": "a3b72babd8afa155-SAN",
      "connection": "keep-alive",
      "content-length": "249",
      "content-type": "application/json",
      "date": "Tue, 15 Sep 2026 11:07:57 GMT",
      "server": "cloudflare"
    },
    "responseBody": "{\"model\":\"muse-spark-1.3-contributor-free\",\"error\":{\"param\":null,\"type\":\"invalid_request_error\",\"message\":\"Error from provider (Console): Upstream request failed: [invalid_request_error] reasoning `encrypted_content` was not issued to this caller\"}}",
    "metadata": {
      "url": "https://opencode.ai/zen/v1/responses"
    }
  }
}
```

### Forensic Takeaways
1. **Status Code 400 Non-Retryable:** The upstream gateway explicitly flags the request with `isRetryable: false`. Retrying without modifying request contents produces identical failures.
2. **Provider Enforcement:** The validation failure occurs at the provider gateway layer before model inference starts.
3. **Session Poisoning:** Because OpenCode records the failed assistant response into SQLite as an error node, the conversation graph remains blocked on that branch.

---

## 4. SQLite Record Forensic Analysis

### Contaminated Record Structure in `part` Table

```json
{
  "type": "reasoning",
  "text": "",
  "time": {
    "start": 1789470272922,
    "end": 1789470273142
  },
  "metadata": {
    "openai": {
      "itemId": "rs_6aa926403b24a1ed202145c1:rs_01a0a4bd6cf975a2ad019323646a8ccf",
      "reasoningEncryptedContent": "Q-PaDgGv-a2T03W6aSU-tez8986_5_QjQlrMkBkNPRV0RkaLKX7pdljqOjyfw3i1-3a0rvAjfTZoliJ7KwmikrmhEbPfNh7G98wdK2znN1t-6i79gaMLyxKLOMQU_XYR5ZEpvevKBZUbEDJL8vIQgM-qsfO0VJTRvwvL-QnXZ-SK34cNeguqn1V4UIpPHhPy5ySVKFCd48zqOQP_u8qlgY0wEpswKO-VAA7xoWZI58AkDHsiDRWZJ686qdhMH6ENelJA1EVhDL-4VfUsTg5KPThLiTisqkTxVej1I8cJeWaoWc3ef81G8AqCsCYgKrkzvkX2He8hvPZp3ZhO9hWAug_RXd3RjV217ya9l8b0AKy_ZQzmKBWQPS8FLokGEkOy8BAXEo7pUC2ISwGPH9xCMyjlqPPhBJLuFJz7ZZnnooGF12VsbH-ik8UuJ2g2e0p5U8E-cEqFSovYL8YHBuh_6JnU9q-TSpVm23DxVRyWg43lvATb4vZfQlWb5QK1-Typ-al8Sf_Sy1YiPha_8IwtGMhmHvxzHF1vLpH-ORhzDJ_QMthtp7K5SD0U3iVvhmDcNdL_njCN8oY_hSOZ4XAXQMBxl2J8joy8L11Kb2Jc-hlIDOl65j5gvwjFhRt3uaZoTaFBiLyQn1RBadKNC7Y30F7_CQdeYyfWHgk0DxpM1i7bHl8VRxHVnwv4QkMGOGEjVN73Md_i6V_bp4NxHsTAmeX_PijA4OYbnxTPMt3LCZEe7rJnXmam5YbicMcVUd8b-U05m-mN-t4vVL_CXivuaBzkQBMrFLSJMvSHHUm8K573Jrex3TKCI2Ayo9NlXVx4VEhuvGSgTmWwA4Rb3BVezdr3rq3qDBbTD4iY7le9L7kL4VVueYRdYuiB9QWY5wkzJSgcPCUgnloGQDF2_EDXBAc1MV2Ig6DOl9-Q4R65sW6jWf725Q4bv3sKwX3q07W5GiLgklOU6nbO9ANZF41wbcUBWi9rEp2WQT_bwoMIuPZz6_GMXX9N3RPNwqtoChqkWVYiRX-PEp9X6_wa8tbCueuogfOfgDfOTR-buIt9FfOnSjHmSBfCK2Ed3HL9xlpfcvuWM9bmd5FLN27X4bkUzhZ370Pa39-xELirAX1YJuWQ1ItZlc8w7fl8uqNYA6RiTm3XKv2hX0TQfX-zaWpOto9Em-fJ6bJO5x0VMUN9iYSxlgMsYJgV3TQrDgRwJ6g8gtb9oAbwXqDzuyKLM6jKKnZMWLYmbZmk-kW0gjN3UpEqMcplYRM2e-jv-PTc7GArMnUAqu3PDYOq9MUFgcE2SH69BuyQgpfy0YLmcS2br_b_9RHYXEeyjn49-um-3p9dK4KS0-5XxEaIY_5xNA2__UFpXqgpExe26ySFQvbZCFF3ffwirG01sSvOIKnSqxwsidupGztj8s1Qz2cQWw"
    }
  }
}
```

### Post-Sanitization Record Structure
Following execution of `sanitize_db.py`, the record retains valid schema formatting while the invalid cryptographic key is eliminated:

```json
{
  "type": "reasoning",
  "text": "",
  "time": {
    "start": 1789470272922,
    "end": 1789470273142
  },
  "metadata": {
    "openai": {
      "itemId": "rs_6aa926403b24a1ed202145c1:rs_01a0a4bd6cf975a2ad019323646a8ccf"
    }
  }
}
```

The absence of `reasoningEncryptedContent` allows the serializer to gracefully bypass token replay, resolving the error permanently without degrading context or loss of workspace diffs.
