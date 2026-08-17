from __future__ import annotations

import argparse
import json
from pathlib import Path

from plugin.backend.app.api_execution import ApiExecutionService
from plugin.backend.app.database import PluginDatabase


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute frozen API snapshots locally.")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--environment-id", required=True)
    arguments = parser.parse_args()
    database_path = arguments.database.resolve()
    database = PluginDatabase(f"sqlite:///{database_path.as_posix()}")
    result = ApiExecutionService(database).execute(
        arguments.baseline_id,
        environment_id=arguments.environment_id,
    )
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
