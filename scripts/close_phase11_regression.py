from __future__ import annotations

import argparse
import json
from pathlib import Path

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.regression import RegressionService


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 11 regression and close a bug.")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--bug-id", required=True)
    parser.add_argument("--baseline-report-id", required=True)
    parser.add_argument("--api-run-id", required=True)
    parser.add_argument("--ui-run-id", required=True)
    args = parser.parse_args()
    database = PluginDatabase(f"sqlite:///{args.database.resolve().as_posix()}")
    result = RegressionService(database).close_bug(
        bug_id=args.bug_id,
        baseline_report_id=args.baseline_report_id,
        regression_api_run_id=args.api_run_id,
        regression_ui_run_id=args.ui_run_id,
    )
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
