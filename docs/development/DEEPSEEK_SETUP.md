# DeepSeek Setup

Status: Phase 5A local setup. Do not commit the local .env file.

## Official configuration

The verified official OpenAI-compatible base URL is https://api.deepseek.com and the Phase 5A
model is deepseek-v4-pro. The legacy aliases deepseek-chat and deepseek-reasoner are rejected.
Official references:

- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/api/list-models
- https://api-docs.deepseek.com/guides/json_mode/
- https://api-docs.deepseek.com/guides/thinking_mode

Create the ignored .env from .env.example and set DEEPSEEK_API_KEY locally. Never paste a key into
source, commands, logs, screenshots, databases, reports, or Git. The verification launcher loads
only an allowlist of variables into the child process environment and never prints their values.

The real adapter sends response_format type json_object, includes the word json and a short example
in each relevant prompt, sets max_tokens explicitly, and sends thinking type disabled. Thinking is
disabled because the task requires strict JSON and all completeness guarantees come from bounded
batches plus local schema/domain validation. Reasoning content is neither needed nor stored.

## Commands

Offline validation, which never creates a paid call:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_phase5a.ps1

Real validation requires both switches and must be run only after explicit cost confirmation:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_phase5a.ps1 -RealLLM -ConfirmPaidCall

The second command creates or reuses the ignored local instance/plugin.db. A successful repeat with
the same content/configuration reuses the idempotent completed run rather than paying again.

## Failure behavior

Missing configuration is BLOCKED. Network, timeout, authentication, balance, rate-limit, provider,
JSON, schema, domain, truncation, or aggregate errors are recorded truthfully as failed or blocked.
No failure silently changes provider_mode to mock.
