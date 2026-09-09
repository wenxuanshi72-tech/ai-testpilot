# Evidence Trust API

Status: authenticity hardening step 7 implemented and locally accepted.

Step 7 exposes the Step 6 deterministic evaluator through
`POST /api/v1/evidence-trust/evaluations`. The request contains a Run ID and an optional
reproduction package directory name. The server resolves both beneath configured, trusted artifact
roots; callers cannot submit absolute paths, separators, traversal components, or arbitrary files.

The endpoint is read-only. A well-formed missing Run truthfully returns an `UNVERIFIED` evaluation;
malformed identifiers return `422`. Valid requests return the versioned evaluator report with the
normal API request ID envelope. The service does not write trust state to the database, modify
artifacts, execute tests, call a provider, or upgrade historical evidence.
