# Plugin Evidence and Classification Test Plan

## Acceptance checks

1. Apply migrations 0001 through 0010 to isolated databases and verify upgrade compatibility.
2. Consolidate completed API and UI runs from the same frozen baseline and environment.
3. Reject incomplete result sets, mismatched contexts, corrupt hashes, unsafe paths, and
   unredacted or sensitive evidence.
4. Persist one authoritative classification per source result and immutable evidence metadata.
5. Confirm the seeded API and UI failures map to `BUG-AUTH-001` without changing their verdict.
6. Confirm advisory analysis is schema-valid, labelled non-authoritative, and cannot alter verdicts.
7. Run the Plugin backend suite, repository Python suite, Ruff, mypy, migration checks, SQLite
   integrity checks, foreign-key checks, secret scanning, and `git diff --check`.

## Phase boundary

No DeepSeek call, formal Bug artifact, test report, SUT bug fix, or Phase 9 implementation is part
of this plan.
