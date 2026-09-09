from __future__ import annotations

from pathlib import Path

from flask import Flask
from flask.testing import FlaskClient

from plugin.backend.tests.test_bug_reproduction import _pair, _writer


def test_api_reports_executed_and_verified_from_fixed_roots(
    app: Flask, client: FlaskClient, tmp_path: Path
) -> None:
    source, reproduction = _pair(tmp_path)
    package = _writer(tmp_path, source, reproduction).write()
    app.config["RUN_ARTIFACT_BUNDLE_ROOT"] = str(source.parent)
    app.config["BUG_REPRODUCTION_ROOT"] = str(package["package_path"].parent)

    executed = client.post("/api/v1/evidence-trust/evaluations", json={"run_id": source.name})
    verified = client.post(
        "/api/v1/evidence-trust/evaluations",
        json={
            "run_id": source.name,
            "reproduction_package_name": package["package_path"].name,
        },
    )

    assert executed.status_code == 200
    assert executed.get_json()["data"]["state"] == "EXECUTED"
    assert verified.status_code == 200
    assert verified.get_json()["data"]["state"] == "VERIFIED"


def test_api_rejects_paths_and_malformed_identifiers(client: FlaskClient) -> None:
    attempts = (
        {"run_id": "../manifest.json"},
        {"run_id": "RUN-" + "A" * 32, "reproduction_package_name": "../package"},
        {"run_id": ["RUN-" + "A" * 32]},
    )

    for payload in attempts:
        response = client.post("/api/v1/evidence-trust/evaluations", json=payload)
        assert response.status_code == 422
        assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_api_requires_json_object(client: FlaskClient) -> None:
    assert client.post("/api/v1/evidence-trust/evaluations", data="x").status_code == 415
    assert client.post("/api/v1/evidence-trust/evaluations", json=[]).status_code == 400


def test_missing_well_formed_run_is_truthfully_unverified(client: FlaskClient) -> None:
    response = client.post("/api/v1/evidence-trust/evaluations", json={"run_id": "RUN-" + "A" * 32})

    assert response.status_code == 200
    assert response.get_json()["data"]["state"] == "UNVERIFIED"
