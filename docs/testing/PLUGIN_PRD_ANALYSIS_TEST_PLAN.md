# Plugin PRD Analysis Test Plan

Status: Phase 5A implementation verification.

## Objective

Prove that Plugin PRD analysis is attributable, bounded, resumable, schema-valid, domain-valid,
secret-safe, and atomic. Mock tests validate deterministic behavior offline. A separately marked
real_llm acceptance proves the paid DeepSeek path only after explicit confirmation.

## Coverage

- Flask application creation, health, stable request IDs, and safe errors.
- Project creation, PRD import, UTF-8/media validation, content hash, and immutable versions.
- Empty Key, official URL/model enforcement, real/Mock separation, and no fallback.
- Official JSON Output request body and explicit disabled thinking mode.
- PRD normalization, section planning, bounded multi-batch behavior, and stable hashes.
- Empty content, malformed/unclosed JSON, Markdown fence cleanup, abnormal finish reason, output
  token-limit risk, false completion marker, and count mismatch.
- Stable source block IDs/line ranges; exact continuous excerpts; wrong blocks; paraphrases;
  discontinuous joins; CRLF/LF; unique NFC/Unicode whitespace resolution; duplicate ambiguity;
  unsupported claims; Schema/domain/aggregate completeness.
- Failed-batch retry, large-batch splitting, immutable failed runs, linked recovery attempts,
  outline/validated-batch reuse, and proof that only the failed batch invokes the provider.
- Candidate isolation, partial failure with zero formal rows, atomic promotion, redacted response
  and parsed-output persistence, immutable reference audits, requirement requery, and database
  secret exclusion.
- Preservation of username length at least six plus registration, login, current-user, and logout.
- Deterministic same-requirement constraint extraction from source excerpts, including bounded
  Arabic/full-width, English-number-word, and Chinese-number forms; maximum, exact, unrelated,
  cross-requirement, ambiguous, and malformed constraints must not satisfy the minimum rule.
- Saved-result offline revalidation with immutable parent/child failures, validator-version audit,
  zero provider calls, idempotent attempts, 19 candidate links, and transaction rollback proving
  that partial promotion cannot leave formal requirements or constraint audits.
- Existing SUT Python tests, strict known-defect XFAIL, Phase 3 live API suite, frontend tests, and
  both frontend builds.

## Gates

Ruff format, Ruff lint, strict mypy, default pytest, Plugin coverage at least 85 percent, schema and
prompt validation, Prettier, ESLint, TypeScript, frontend tests, both builds, live Phase 3
black-box regression, git diff check, secret scan, ignored database check, and phase-boundary scan
must pass. A saved real result may become queryable only through an independently audited offline
revalidation attempt when the stored evidence proves a deterministic validator false negative;
the original real runs remain immutable failures and the offline attempt must record zero calls.

The default test selection excludes black_box and real_llm so routine local tests cannot incur
fees or depend on separately running services.
