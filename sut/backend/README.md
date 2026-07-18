# SUT Flask Authentication Backend

Phase 2 implements the SUT authentication API with an application factory, layered validation and
services, migration-managed SQLite persistence, and opaque server-side sessions.

## Local commands

```powershell
$env:FLASK_APP = "sut.backend.wsgi:app"
.\.venv\Scripts\flask.exe db upgrade
.\.venv\Scripts\python.exe -m sut.backend.wsgi
```

The default loopback address is `http://127.0.0.1:5001`. The default database is
`instance/sut.db`, which is ignored and must never be committed. Override it with
`SUT_DATABASE_URL`; tests inject isolated temporary database URLs explicitly.

## Security boundary

The browser cookie contains an opaque token and the database contains only its hash. Passwords use
Werkzeug hashing. Credentialed CORS and browser mutation origins use exact configured origins.

`REQ-AUTH-USERNAME-001` still requires at least six characters, but this Phase 2 implementation
deliberately omits that one minimum-length validation so `z1234 / Test1234` incorrectly registers.
Do not fix it before the authorized regression phase.
