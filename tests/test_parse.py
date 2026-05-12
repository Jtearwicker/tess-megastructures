"""Tests for tess_megastructures.ingest.parse.

The canonical test pattern: parse the fixture XML, compare to the
expected output dict in fixtures/expected_parse.json. This catches
schema-shift breakage and regressions from refactors.

The fixture is committed; to update it, run scripts/regenerate_parse_fixture.py
(to be added) and review the diff.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Implement after parser refactor and fixture capture")
def test_parse_example_xml(example_xml, fixtures_dir):
    """Parser produces expected output for the canonical fixture."""
    pass


@pytest.mark.skip(reason="Implement after parser refactor")
def test_parse_handles_missing_uncertainty():
    """Parser does not crash when an XML attribute lacks the 'uncertainty' field."""
    pass


@pytest.mark.skip(reason="Implement after parser refactor")
def test_parse_handles_no_tces():
    """Parser returns an empty list for an XML with no planetResults."""
    pass


@pytest.mark.skip(reason="Implement after parser refactor")
def test_parse_namespace_aware():
    """Parser uses namespace-aware lookup, not positional indexing."""
    pass
