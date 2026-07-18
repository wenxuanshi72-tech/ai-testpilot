# ADR-001: Local-First Modular Monolith

- Status: Accepted
- Date: 2026-07-18
- Decision owners: AI TestPilot project
- Scope: First local release architecture

## Context

AI TestPilot must demonstrate a real PRD-to-regression testing lifecycle without relying on enterprise infrastructure or external deployment. The prototype includes a deliberately separate authentication SUT and a testing product with substantial but closely related workflows: ingestion, LLM orchestration, review, execution, evidence, bug/report generation, and traceability.

A distributed architecture would add deployment, queue, network, observability, and consistency costs before the closed loop is proven. Combining the SUT and plugin would undermine test realism and data ownership.

## Decision

Build the first release as a **local-first modular monolith for the plugin**, paired with a **separately deployed SUT**. Each system has its own React frontend, Flask-based backend, process boundary, and SQLite database. Plugin modules depend inward on application/domain contracts; provider, database, HTTP/Playwright, filesystem, and task mechanisms are adapters.

The accepted local topology uses loopback services and ignored local runtime artifacts. A background-task interface is defined independently of its first local implementation so durable workers can replace it later.

## Rationale

- Local operation is repeatable, affordable, reviewable, and suitable for a portfolio demonstration.
- A modular monolith preserves explicit domain boundaries without premature distributed-system failure modes.
- A separate SUT forces the plugin to use real public API/UI contracts and keeps `sut.db` isolated from `plugin.db`.
- SQLite is portable, zero-administration, easy to reset for local test data, and adequate for single-machine prototype concurrency.
- Fewer operational components make evidence/traceability defects easier to diagnose while the domain is evolving.

## Consequences

### Positive

- Fast local setup and deterministic demonstrations.
- Clear repository/process/database ownership.
- Transactional plugin workflows and simpler migrations.
- Low infrastructure cost and no cloud prerequisite.
- Domain/adapter separation remains visible and testable.

### Trade-offs

- SQLite has limited concurrent writes and production operational features.
- In-process/local tasks have weaker durability and horizontal scalability than a queue.
- Local files require explicit size, retention, access, and backup handling.
- Hosted multi-user authorization, isolation, and observability are deferred.
- Module boundaries require review discipline because one process does not enforce them physically.

## Migration boundaries

Repositories and domain services must avoid SQLite-specific invariants. Stable IDs, UTC timestamps, portable constraints, explicit ordering, immutable versions, and schema migrations support a future PostgreSQL adapter. A migration must reconcile counts, IDs, hashes, statuses, and trace completeness.

The task interface stores durable task/batch/idempotency state so a later queue/worker can replace in-process execution. Evidence storage uses an adapter so local files can later move to object storage. Online deployment additionally requires HTTPS, managed secrets, authentication/authorization, tenant isolation, isolated browser workers, restricted egress, monitoring, backups, retention, cost controls, and rollback.

These replacements cannot change AI/deterministic authority, provenance, trace semantics, export formats, or the accepted local mode.

## Rejected alternatives

- **Single combined SUT/plugin application:** rejected because it weakens realistic black-box testing and database boundaries.
- **Microservices from the start:** rejected as premature operational complexity.
- **Cloud-first/SaaS requirement:** rejected because it makes the core demonstration dependent on external services and cost.
- **One shared database:** rejected because cross-domain joins would bypass public SUT behavior.

## Validation

Later gates must prove separate processes/databases, no plugin access to SUT internals, local closed-loop repeatability, module dependency rules, and portable persistence contracts. Phase 1 records the structure only and creates no database or service.
