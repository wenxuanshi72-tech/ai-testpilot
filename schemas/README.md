# Versioned Schemas

JSON Schemas are versioned by domain and validated with JSON Schema Draft 2020-12. Runtime readers
accept only explicitly supported versions and never guess fields from a newer contract.

Current domains include requirements, test intents/cases, reviews, execution snapshots/results,
evidence, Bugs, reports, Run Bundles, Action Tape events, and reproduction results.

The authenticity contracts introduced after Phase 13 are:

- `run-bundles/v1/run_manifest.schema.json` (`run-manifest@1.0.0`)
- `action-tape/v1/action_tape_event.schema.json` (`action-tape-event@1.0.0`)
- `reproduction/v1/reproduction_result.schema.json` (`reproduction-result@1.0.0`)

These Schemas define data eligibility but do not themselves prove runtime implementation. Cross-file
rules such as unique Artifact paths, complete evidence-role coverage, canonical bundle hashing and
ownership resolution also require the versioned domain verifier defined by the trust model.
