# Phase 11 Traceability and Regression

Status: implemented and locally accepted

Phase 11 fixes the authorized minimum-six-character registration rule and proves the fix with the
same immutable test versions frozen in baseline `FBL-5BCEA5DA11144E9BB47C545AD73919DD`.
Login normalization remains unchanged; the minimum applies only to registration. The React client
submits the real registration request and maps the backend `too_short` detail to the explicit
message `Use at least 6 characters.`. This preserves the frozen UI contract that checks HTTP 400,
the `/register` route, and visible validation feedback.

Migration `0013_traceability_regression.sql` adds append-only regression runs and bug status events.
The canonical `BUG-AUTH-001` v1 row, Phase 7 failures, Phase 8 evidence, Phase 9 bundle, and Phase 10
report remain immutable. Closing the bug requires all of the following deterministic checks:

- the baseline Bug and report hashes are intact;
- baseline and regression runs reference the same frozen baseline;
- every case ID, case version, and immutable snapshot ID is unchanged;
- both seeded cases transition from `FAIL` to `PASS`;
- the API observes expected and actual HTTP 400;
- the UI remains on `/register`, observes `POST /api/auth/register` HTTP 400, and passes its frozen
  visible assertion;
- registration, login, current-user/authentication protection, and logout guards pass.

The original canonical Bug remains readable with status `open` as an immutable historical record.
Its effective lifecycle is derived from the append-only `bug_status_events` close event. Phase 12
is not implemented or started here.
