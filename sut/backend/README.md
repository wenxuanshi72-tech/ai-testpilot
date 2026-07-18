# SUT Backend Boundary

This directory is reserved for the Python 3.11/Flask system-under-test backend. Phase 1 contains no Flask application, route, model, migration, database, or authentication behavior. Shared dependency groups and quality configuration live in the root `pyproject.toml`.

Implementation begins only in the explicitly authorized SUT backend phase and must preserve the seeded username-length defect until its regression-fix phase.
