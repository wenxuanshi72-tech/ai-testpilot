# Protected Seeded Defect Plan

Status: active from Phase 2 until the authorized regression-fix phase

## Trace identity

- Requirement: `REQ-AUTH-USERNAME-001`
- Future API case: `TC-API-AUTH-REG-005`
- Future UI case: `TC-UI-AUTH-REG-005`
- Planned defect: `BUG-AUTH-001`

## Requirement expectation

A username shorter than six characters is rejected with a clear validation error. The PRD, SRS, API
case, and UI case retain this expectation.

## Seeded defective implementation

The Phase 2 SUT deliberately omits minimum username length validation in application validation and
database constraints. Maximum length, allowed characters, uniqueness, password, and session security
remain enforced. `z1234 / Test1234` must therefore be persisted and return `201`. This is an
intentional product defect, not correct behavior.

## Internal sentinel test

`test_seeded_defect_allows_five_character_username` asserts the current defective `201` response.
It prevents accidental early repair and is not a formal requirement-acceptance test. It must not be
renamed or presented as evidence that the six-character requirement passes.

## Future generated acceptance tests

The formal API and UI tests will expect `z1234` to be rejected. Before repair, their observed success
must deterministically produce `FAIL` with product-bug classification and real evidence. Assertions
must not be weakened, skipped, or rewritten to accommodate the SUT.

## Fix and regression plan

Only the explicitly authorized regression-fix phase may add the missing minimum-length validation.
That phase updates/removes the internal sentinel, reruns the unchanged formal API/UI expectations,
preserves baseline evidence, verifies surrounding authentication controls, and closes
`BUG-AUTH-001` only after both formal paths pass.
