# Plugin Backend Boundary

This directory is reserved for the Python 3.11/Flask AI TestPilot backend. Phase 1 contains no provider adapter, PRD analysis, persistence, execution, evidence, bug, or reporting implementation. Shared dependency groups and quality configuration live in the root `pyproject.toml`.

Later modules must follow the approved domain/adapter boundaries and cannot give AI authority over deterministic test verdicts.
