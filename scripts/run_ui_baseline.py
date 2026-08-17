from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.ui_execution import UiExecutionService
from sut.backend.app import create_app as create_sut_app
from sut.backend.app.extensions import db as sut_db

ROOT = Path(__file__).resolve().parents[1]


def _wait(url: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310 - localhost only
                if response.status < 500:
                    return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"LOCAL_SERVICE_NOT_READY:{url}")


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen UI snapshots with Playwright.")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--environment-id", required=True)
    parser.add_argument("--browser-channel", default="msedge")
    arguments = parser.parse_args()
    runtime_root = ROOT / "tmp" / "phase7b-runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="ui-run-", dir=runtime_root, ignore_cleanup_errors=True
    ) as temporary:
        temporary_path = Path(temporary)
        sut_database = temporary_path / "sut.db"
        sut_url = f"sqlite:///{sut_database.as_posix()}"
        sut_app = create_sut_app({"SQLALCHEMY_DATABASE_URI": sut_url, "TESTING": True})
        with sut_app.app_context():
            sut_db.create_all()
            sut_db.session.remove()
            sut_db.engine.dispose()
        environment = os.environ.copy()
        environment.update(
            {
                "SUT_DATABASE_URL": sut_url,
                "SUT_CORS_ALLOWED_ORIGINS": "http://127.0.0.1:5173",
                "SUT_SESSION_COOKIE_SECURE": "false",
                "VITE_SUT_API_BASE_URL": "http://127.0.0.1:5001",
                "TEMP": str(temporary_path),
                "TMP": str(temporary_path),
            }
        )
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        backend_log = (temporary_path / "backend.log").open("wb")
        frontend_log = (temporary_path / "frontend.log").open("wb")
        backend = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "sut.backend.wsgi",
            ],
            cwd=ROOT,
            env=environment,
            stdout=backend_log,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
        node = shutil.which("node")
        if not node:
            raise RuntimeError("NODE_NOT_FOUND")
        frontend = subprocess.Popen(  # noqa: S603 - resolved installed node, fixed local script
            [
                node,
                str(ROOT / "node_modules" / "vite" / "bin" / "vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
            ],
            cwd=ROOT / "sut" / "frontend",
            env=environment,
            stdout=frontend_log,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
        try:
            _wait("http://127.0.0.1:5001/api/health")
            _wait("http://127.0.0.1:5173/register")
            database = PluginDatabase(f"sqlite:///{arguments.database.resolve().as_posix()}")
            database.migrate()
            result = UiExecutionService(database).execute(
                arguments.baseline_id,
                environment_id=arguments.environment_id,
                base_url="http://127.0.0.1:5173",
                browser_channel=arguments.browser_channel,
            )
            print(json.dumps(result, sort_keys=True))
        finally:
            _stop(frontend)
            _stop(backend)
            frontend_log.close()
            backend_log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
