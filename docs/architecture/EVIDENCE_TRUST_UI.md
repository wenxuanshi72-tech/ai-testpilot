# Evidence Trust UI

Status: authenticity hardening step 8 implemented and locally accepted.

Step 8 adds an Independent Trust Inspector to the existing Evidence Vault. A reviewer supplies a
Run ID and optional reproduction package name, explicitly starts evaluation, and receives the
recomputed trust state, deterministic reason, Bundle hash, reproduction Result link, and policy and
evaluator versions from the Step 7 API.

The interface does not infer trust from existing workspace or database labels. It clears stale
results before every request, never presents an API failure as a trust state, supports keyboard and
label-based form operation, announces successful results, and collapses to one column on small
screens. It does not mutate evidence, persist status, execute tests, or call an AI provider.
