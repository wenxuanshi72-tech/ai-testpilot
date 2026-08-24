# Phase 13 Portfolio MVP End-to-End Test Plan

Status: portfolio MVP scope accepted; no further paid generation required

## Objective

Phase 13 demonstrates the complete local portfolio story without claiming production-grade
regeneration of every AI candidate. The accepted path is:

```text
real DeepSeek PRD analysis
→ 19 structured Requirements
→ reviewed historical candidate collection
→ 10-case frozen MVP baseline
→ real deterministic API and Playwright results
→ persisted evidence and failure classification
→ BUG-AUTH-001 and Markdown/HTML/PDF report
→ authorized SUT fix
→ same-case FAIL-to-PASS regression
→ append-only Bug closure
```

The verifier is `scripts/verify_phase13_portfolio_mvp.py`. It opens databases read-only, recomputes
canonical hashes and trace invariants, and performs no Provider call or business-data write.

## Truthful scope boundary

- The real Analysis Run `ANR-8D946E45913A418F899774282E8121C2` is accepted as the Phase 13
  Provider evidence. It used DeepSeek Real with `deepseek-v4-pro`, completed three content calls,
  and atomically stored 19 Requirements.
- The 44-slot/18-batch candidate-regeneration experiment is retained as engineering evidence, not
  an acceptance dependency. Its failed Sessions and costs remain immutable and visible.
- Phase 13 does not claim that those 44 candidates were promoted, reviewed, or executed.
- The execution half reuses the approved portfolio MVP baseline
  `FBL-5BCEA5DA11144E9BB47C545AD73919DD`, which contains ten immutable snapshots produced by the
  accepted Phase 5B/6 workflow.
- Reuse is explicit. Existing real results are verified; they are not copied into fabricated new
  Run IDs and are not presented as a new clean-room execution.

## Mandatory verification gates

1. The Analysis Run exists, is `succeeded`, identifies DeepSeek Real and `deepseek-v4-pro`, has
   HTTP 200/`finish_reason=stop` call evidence, and owns exactly 19 Requirements.
2. Both the analysis database and the accepted Plugin database pass SQLite `integrity_check` and
   have zero foreign-key violations.
3. The MVP baseline is frozen and contains exactly ten snapshots whose hashes recompute.
4. The pre-fix canonical report links real API and UI runs containing failures.
5. `BUG-AUTH-001` v1 links exactly `TC-API-AUTH-REG-005` and `TC-UI-AUTH-REG-005` and its canonical
   hash recomputes.
6. The canonical report hash recomputes from the same persisted record.
7. Regression uses the same frozen baseline and records both seeded transitions as `FAIL→PASS`.
8. The regression trace hash recomputes and the append-only Bug status event is `open→closed`.
9. The verifier reports zero new Provider calls and zero new Runs.
10. All historical Phase 13 generation failures remain documented; no result is relabelled PASS.

## Quality and safety

Run the focused verifier tests, complete Plugin/backend and repository gates, Ruff, mypy,
front-end checks/builds as applicable, `git diff --check`, database checks, and a sensitive-data
scan. `.env`, databases, logs, screenshots, traces, and generated reports remain ignored runtime
data. No secret content is read or printed.

Phase 14 may begin only when the verifier and quality gates pass and the results document clearly
states the reuse boundary above.
