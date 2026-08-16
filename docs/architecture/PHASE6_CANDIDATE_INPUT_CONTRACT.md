# Phase 6 Candidate Input Contract

## Read-only boundary

Phase 6 may consume a collection only when its Phase 5B run state is `validated_pending_review` through `GET /api/v1/test-generation-runs/{run_id}/candidate-collection`. It must verify the collection hash, candidate hashes, candidate count, formal requirement version/snapshot links, primary requirement links, and coverage matrix before offering any review action. Reading creates no review, approval, baseline, or snapshot.

## Implemented in Phase 6

Phase 6 owns human approve/reject/request-changes decisions, approved versions, protocol freezing,
frozen baseline membership, and immutable execution snapshots. Migration 0006 and the versioned
review/freeze service implement these capabilities without changing Phase 5B candidate records.
The caller must supply a real reviewer identity; AI candidates are never automatically approved.

阶段5B产物尚未经过人工审核，不得直接用于正式执行；必须在阶段6批准和冻结后才能成为执行基线。
