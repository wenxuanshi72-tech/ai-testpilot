# Plugin backend

Phase 5A implements the local Flask API for project/PRD persistence and attributable,
schema-validated PRD requirement analysis. It owns `plugin.db` and never reads `sut.db`.

Run migrations and the local API from the repository root:

```powershell
.\.venv\Scripts\python.exe -m plugin.backend.migrate
.\.venv\Scripts\python.exe -m plugin.backend.wsgi
```

Real calls require `DEEPSEEK_API_KEY` in the process environment and explicit
`provider_mode=real`. There is no real-to-mock fallback.
Saved real candidates can be revalidated without a provider only through the audited
`OfflineRevalidationService`. It preserves failed real runs, records validator provenance and zero
LLM calls, and promotes requirements only after complete deterministic validation succeeds.
