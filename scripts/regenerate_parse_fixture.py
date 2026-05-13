"""Generate ``tests/fixtures/expected_parse.json`` from the committed XML fixture.

Run this:

- After you first set up the fixture (one-time bootstrap).
- After any INTENTIONAL change to the parser's output schema or
  computed values. Carefully review the resulting diff before committing.

Do NOT run this to "fix" a failing smoke test. A failing smoke test
means the parser changed in a way you might not have intended — that's
the point of the test.

Usage:
    uv run python scripts/regenerate_parse_fixture.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    # Ensure the package is importable (uv run handles this in editable mode).
    from tess_megastructures.ingest.parse import parse_dv_xml

    fixture_xml = repo_root / "tests" / "fixtures" / "example_dv.xml"
    expected_json = repo_root / "tests" / "fixtures" / "expected_parse.json"

    if not fixture_xml.exists():
        print(f"ERROR: fixture XML not present at {fixture_xml}")
        print("Run scripts/download_test_fixture.py first.")
        return 1

    print(f"Parsing {fixture_xml.name}...")
    rows = parse_dv_xml(fixture_xml)
    print(f"  -> {len(rows)} TCE(s)")

    # Strip volatile fields that change run-to-run.
    volatile = {"parser_version", "parsed_at"}
    clean_rows = [{k: _jsonify(v) for k, v in row.items() if k not in volatile} for row in rows]

    payload = {
        "schema_version": 1,
        "source_fixture": fixture_xml.name,
        "n_rows": len(clean_rows),
        "rows": clean_rows,
    }

    expected_json.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"  -> wrote {expected_json}")
    print(f"     Review the diff with `git diff {expected_json}` before committing.")
    return 0


def _jsonify(value):
    """Convert NaN/inf to None so the JSON round-trips cleanly."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


if __name__ == "__main__":
    sys.exit(main())
