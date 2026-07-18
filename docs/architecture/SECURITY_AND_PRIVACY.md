# Security and Privacy Design

Status: Phase 0 threat model and future acceptance contract. These controls are planned; Phase 0 does not claim they are implemented or tested.

## Security objectives and trust boundaries

Protect credentials, authentication state, uploaded PRDs, test data, model traffic, databases, evidence, and exported artifacts while keeping deterministic execution limited to explicitly authorized local targets. Treat browsers, uploads, PRDs, provider responses, LLM output, SUT responses, filenames, and generated content as untrusted.

Primary boundaries are browser-to-SUT, browser-to-plugin, plugin-to-provider, executor-to-allowlisted SUT, application-to-database, and application-to-local artifact store. SUT and plugin use separate databases and least-privilege processes.

## Secret management and Git hygiene

- API keys and environment secrets are supplied only through process environment variables or a future approved secret manager.
- `.env` and `.env.*` are ignored; only `.env.example` with safe placeholders is versioned.
- Never place secrets in source, prompts committed to Git, URLs, databases, logs, evidence, screenshots, reports, task payloads, or error messages.
- Startup validates required configuration without echoing values. Key rotation and revocation are operational requirements.
- Pre-commit/CI secret scanning and repository-history review are later gates. Suspected exposure blocks release and triggers revocation; deletion from the latest file is insufficient.
- SQLite databases, evidence, generated reports, caches, and runtime logs are excluded from Git.

## Passwords and session authentication

Passwords use an approved adaptive password-hashing function with per-password salt and tuned work factor. Plaintext passwords/confirmations are held only as briefly as necessary, compared safely, never logged/stored, and excluded from model input.

The SUT uses a server-side opaque session, not JWT. The browser cookie contains a high-entropy opaque token; the database stores only its one-way hash. Cookies are `HttpOnly`, `SameSite=Lax`, narrowly scoped, and `Secure` under HTTPS. Sessions have idle/absolute expiry, rotation after authentication, explicit logout revocation, and server-side invalidation. Authentication errors avoid user enumeration.

The protected username-length defect does not authorize weakening password or session controls.

## CSRF and CORS

State-changing cookie-authenticated requests require an origin-checked CSRF design such as synchronizer token or signed double-submit token. Safe methods remain side-effect free. Login/logout CSRF is considered explicitly. Tokens are session-bound, time-bounded where appropriate, and never exposed in URLs/logs.

CORS uses exact configured local origins, methods, and headers; credentialed requests never use wildcard origins. Preflight behavior is tested. CORS is not authentication or CSRF protection.

## Structured redaction

Redaction occurs before logging/persistence/export and again during artifact validation:

- Headers: remove/mask `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, provider-key headers, CSRF tokens, and configured sensitive names.
- Request bodies: mask password, confirmation, token, secret, key, cookie, session, and fields marked sensitive by the test protocol.
- Response bodies: mask tokens/session/user personal fields and apply endpoint/schema-aware rules.
- Query strings and URLs: remove sensitive parameters before storage.
- Logs/errors: use structured allowlisted fields; no raw object dumps, environment dumps, stack traces in client responses, or absolute user paths.

Masking preserves type/presence and optionally a non-reversible correlation fingerprint, never recoverable secret content. Pattern scanning is defense in depth, not a replacement for structured redaction.

## Screenshot, Trace, HAR, and video privacy

UI test data uses dedicated non-personal accounts. Before screenshots, the executor masks known sensitive locators and avoids capturing password fields. Screenshot review/redaction occurs before formal promotion.

Playwright Trace/HAR/video may contain DOM values, headers, bodies, cookies, URLs, and storage. They are disabled unless needed, stored under restricted evidence access, size/retention capped, and processed through available redaction/sanitization. HAR content embedding is minimized. If safe sanitization is not reliable, the artifact remains restricted or is not captured/exported.

## File upload safety

PRD ingestion permits configured Markdown/plain-text media types and verified extensions/signatures only. The server enforces conservative per-file/request size limits before full buffering, rejects archives/executables in the initial release, normalizes UTF-8 safely, and limits parsing depth/time.

The original filename is display metadata only. Storage uses server-generated IDs and safe extensions. Normalize paths, reject absolute paths, drive/UNC forms, null bytes, reserved names, `..`, separators, alternate streams, and symlink/reparse-point escapes. Resolve the final path and prove it remains under the configured project/artifact root before read/write.

Uploaded content is never executed, imported as code, or served with an active content type.

## Prompt injection and untrusted model output

A PRD may contain instructions that attempt to override system policy, reveal secrets, call tools, or generate executable code. The system labels source text as data, uses task-specific prompts, minimizes exposed context/secrets, restricts tools, and validates output independently. Prompt injection detection can warn/quarantine but never makes the PRD trusted.

LLM output is untrusted data. Strict JSON parsing, versioned Schema, domain rules, reference integrity, length/depth limits, and human review precede promotion. Model-authored Python/JavaScript/shell, arbitrary Playwright code, SQL, URLs, filesystem paths, headers, or commands are never executed. Executors accept only protocol-enumerated operations.

## Target allowlist and SSRF

API/UI executors resolve targets from administrator-configured environment references, not model-provided absolute URLs. Policy restricts scheme, hostname, port, and optional path; initial local mode permits only intended loopback SUT endpoints. DNS/IP is revalidated where relevant, redirects are disabled or rechecked, and credentials cannot be forwarded cross-origin.

Block link-local, metadata, private, multicast, file, UNC, and non-HTTP schemes unless the exact local target is explicitly approved. URL parsing uses a standard library and defenses cover alternative IP encodings and DNS rebinding. Response byte/time limits mitigate resource abuse.

## Evidence access and filesystem boundary

Evidence metadata/content access is project-scoped and least privilege. APIs address evidence IDs, never arbitrary paths. Canonical resolution must remain under `EVIDENCE_ROOT`; downloads set a safe MIME type, disposition, anti-sniffing headers, and authorization check. Hashes detect corruption, not authorization.

Atomic writes, restrictive permissions, random/stable IDs, quotas, and audit logs protect artifacts. Symlinks/reparse points are rejected. Local demonstration processes must not expose artifact directories directly through a general static server.

## Retention and cleanup

Retention is configurable by data class: raw provider responses and verbose logs shortest; screenshots/traces/HAR/video bounded by age/size; canonical results/trace metadata longer for audit. Cleanup is idempotent, logged, respects active/legal holds if later introduced, verifies root containment, and preserves tombstone/hash metadata when lineage requires it. Test accounts/data are isolated per run and cleaned without deleting baseline evidence.

## Local demonstration boundary

Default services bind to loopback, use non-production sample accounts, restrict CORS/targets to configured local URLs, expose no remote tunnel, and avoid shared-machine secrets. `.env`, databases, and artifacts remain local. Demonstration guidance warns that plain HTTP is acceptable only for isolated loopback development and does not represent production transport security.

No network provider call occurs without explicit later-phase configuration and authorization. Phase 0 performs no DeepSeek call.

## Future online deployment requirements

A hosted option requires separate threat modeling and authorization plus HTTPS/HSTS, managed secrets, authenticated users, role/project authorization, tenant isolation, production CSRF/CORS, rate limits, abuse controls, malware/content scanning, isolated browser workers and egress policy, encrypted storage/backups, database least privilege, centralized redacted audit logs, retention/deletion workflows, monitoring/alerting, dependency/container scanning, secure headers, incident response, cost controls, and rollback/recovery validation.

Online deployment cannot weaken local safety or become a prerequisite for the accepted local loop.

## Acceptance evidence required later

Implementation phases must prove these controls with unit/integration/security tests, configuration inspection, secret scans, path traversal/SSRF/CSRF/CORS cases, redaction fixtures, artifact-access checks, session lifecycle tests, upload boundary tests, and a documented residual-risk review. A document or existing file alone is not evidence that a security control works.
