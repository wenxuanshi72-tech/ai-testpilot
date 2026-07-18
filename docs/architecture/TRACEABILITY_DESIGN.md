# Traceability Design

Status: Phase 0 design. IDs and chains shown below are planning examples, not records of an executed test.

## Objective and canonical chain

Traceability must answer what source justified a requirement, which approved case checked it, what exactly ran, what evidence supports the deterministic result, where a defect/report used that result, and whether a fix was verified.

`PRD -> PRD Version -> Analysis Run -> Requirement Version -> Test Case Version -> Test Run -> Test Result -> Evidence -> Bug -> Report -> Regression Result`

Relationships are explicit versioned records, not inferred from narrative text or filenames. AI may propose links with provenance/confidence, but deterministic validation and human review are required before promotion. AI cannot invent a target object that does not exist.

## Stable ID principles

| Entity | Prefix/example | Stability rule |
|---|---|---|
| Project | `PRJ-*` | Stable for workspace lifetime |
| PRD / version | `PRD-*` / `PRDV-*` | Source identity stable; each content revision immutable |
| Analysis run | `ANR-*` | New for each configuration/input execution |
| Requirement | `REQ-*` | Stable semantic identity; revisions use separate version identity |
| Test case / version | `TC-*` / `TCV-*` | Stable intent; edits create immutable version |
| Test run / result | `RUN-*` / `RES-*` | Immutable execution snapshot and outcome |
| Evidence | `EVD-*` | Immutable metadata/hash identity |
| Bug | `BUG-*` | Stable defect identity; status/history versioned |
| Report | `RPT-*` | One canonical export record/version |
| Regression link/result | `RGL-*` / `RES-*` | Explicit baseline-to-regression relation |

IDs are opaque, unique, case-normalized, never recycled, and never based only on mutable titles or array positions. Deterministic matching uses source anchors, canonical fingerprints, and approved history to reuse identity across regeneration. Uncertain matches require review; they do not silently drift or merge.

## PRD versions and source locations

A PRD identity owns immutable versions with content hash, encoding, media type, author/source metadata where safe, and a supersession edge. Requirement versions point to exact PRD version plus one or more source locations: heading path, normalized character/line range, source excerpt hash, and optional page for derived PDF. Changing source content creates a new PRD version and makes impacted downstream links candidates for staleness analysis.

## Requirement and test-case relationships

Requirements and test-case versions are many-to-many through typed links (`verifies`, `guards`, `explores`, `negative_boundary`). Each link records source/target versions, creation source (`human`, `ai_real`, `ai_mock`), prompt/model provenance when relevant, review status, timestamps, and validity interval.

An approved case version records the requirement versions it covers. Approval freezes those links. A later requirement revision marks the link `stale_pending_review`; it does not rewrite the historical approved case.

## Approval and execution snapshot

Case identities have immutable versions and `draft`, `in_review`, `approved`, `rejected`, or `superseded` review state. A test run snapshots approved case version/hash, protocol schema, requirement version links, environment/config reference, non-secret test-data references, executor/browser versions, and creation time. Results always reference this snapshot; later edits cannot alter what ran.

## Results, evidence, defects, reports, and regression

- A result belongs to one run and one case snapshot and records authoritative state/failure type, expected/actual summary, and timing.
- Evidence links many-to-many to results when one artifact supports several facts. The link records evidence role (`request`, `response`, `screenshot`, `trace`, `log`, etc.).
- A bug must link at least one eligible failed result, its requirement/case versions, and required evidence. Advisory AI analysis is a separate attributed field.
- A report links the exact run set, included result/bug versions, generation configuration, artifact hashes, and format versions.
- A regression record links bug, baseline run/result, fix/change reference where available, regression run/result, same-or-reviewed case version, and deterministic comparison outcome.

Old results, evidence hashes, and bug history remain immutable after a fix.

## Integrity checks

### Orphan detection

Report any required object without its mandatory parent/link: requirement without PRD version/analysis, approved case without requirement, result without frozen case/run, evidence without registered result context, formal bug without result/evidence, report without finalized run, or regression without baseline and new result.

### Invalid-reference detection

Foreign keys and application checks reject nonexistent IDs, wrong project ownership, incompatible entity type, duplicate required edge, future version, disallowed status, evidence whose file/hash record is invalid, or cross-environment links not explicitly permitted.

### Staleness detection

A downstream link is stale when its source version/hash changes, an approved case targets a superseded requirement, an execution used a no-longer-approved case, a report excludes a later correction it claims to include, or a regression uses changed test intent without review. Stale does not mean deleted; it requires review/re-execution.

## Metrics

- Requirement coverage = approved in-scope requirements with at least one approved applicable test-case version / all approved in-scope testable requirements.
- API/UI coverage is reported separately by `test_type`; manual-only coverage cannot be presented as automation coverage.
- Trace completeness = required trace edges present and valid / required trace edges expected for objects at their lifecycle state.
- Evidence completeness = finalized results meeting their status/type-specific mandatory evidence set / all finalized results requiring evidence.
- Orphan and stale counts are reported alongside percentages; exclusions require coded reasons.

Metrics use immutable snapshots, state their denominator and timestamp, and never infer success from file existence.

## Planned seeded-defect chain — not executed

The following is a design example only:

```text
PRD-AUTH-001 / PRDV-AUTH-001-V1
  -> ANR-AUTH-001
  -> REQ-AUTH-USERNAME-001 (username length >= 6)
      -> TC-API-AUTH-REG-005 / TCV-API-AUTH-REG-005-V1
      -> TC-UI-AUTH-REG-005  / TCV-UI-AUTH-REG-005-V1
          -> RUN-AUTH-BASELINE-001
          -> planned result and evidence IDs assigned only after real execution
              -> BUG-AUTH-001
                  -> RPT-AUTH-BASELINE-001
                  -> RGL-AUTH-001
                      -> RUN-AUTH-REGRESSION-001 / planned regression result
```

The expected behavior is rejection of `z1234`; the protected pre-fix implementation is planned to accept it. No result/evidence ID or verdict is asserted here because Phase 0 performs no execution.

## Audit and version rules

Creation, review, approval, supersession, staleness acknowledgement, export, purge, and regression-link changes record actor, UTC timestamp, correlation/request ID, reason, before/after version references, and immutable content hashes. Approved records use append-only revision or explicit supersession. Administrative correction never overwrites execution facts.

Trace exports include schema/artifact versions and relative links. Transactional promotion ensures an approved aggregate and its mandatory links become visible together. Scheduled integrity scans and phase gates block formal artifacts when critical links are missing or invalid.
