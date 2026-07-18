from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    # The JUnit file is generated locally by this verifier in its unique temporary directory.
    root = ElementTree.parse(Path(sys.argv[1])).getroot()  # noqa: S314
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    summary = {
        field: sum(int(suite.attrib.get(field, "0")) for suite in suites)
        for field in ("tests", "failures", "errors", "skipped")
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
