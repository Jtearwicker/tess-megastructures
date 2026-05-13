"""Tests for tess_megastructures.ingest.parse.

The smoke test is the most important one: it parses the committed
fixture XML and compares the result to a committed JSON of expected
values. This catches schema-shift breakage and regressions from
refactors.

If you intentionally change the parser's output schema, regenerate
the fixture by running:

    uv run python scripts/regenerate_parse_fixture.py

Then review the diff before committing.
"""

from __future__ import annotations

import io
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tess_megastructures.ingest.parse import (
    _attr_bool,
    _attr_float,
    _attr_int,
    _attr_str,
    _decode_sectors_bitmask,
    _value_over_uncertainty,
    parse_dv_xml,
    parse_sector,
)

# -------------------------------------------------------------------------
# Helpers / fixtures
# -------------------------------------------------------------------------

# Minimal stub XML used by helper tests so they don't depend on the
# large fixture file.
_STUB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<dv:dvTargetResults xmlns:dv="http://www.nasa.gov/2018/TESS/DV"
                    ticId="12345678"
                    planetCandidateCount="0"
                    sectorsObserved="0000000000000000000000000000000000000000000000000000000000001011"
                    startCadence="100" endCadence="200">
  <dv:effectiveTemp value="5500.0" uncertainty="100.0"/>
</dv:dvTargetResults>
"""


@pytest.fixture
def stub_root() -> ET.Element:
    return ET.parse(io.StringIO(_STUB_XML)).getroot()


@pytest.fixture
def fixture_xml(fixtures_dir: Path) -> Path:
    path = fixtures_dir / "example_dv.xml"
    if not path.exists():
        pytest.skip(f"Fixture not present: {path}")
    return path


@pytest.fixture
def expected_parse(fixtures_dir: Path) -> dict:
    path = fixtures_dir / "expected_parse.json"
    if not path.exists():
        pytest.skip(f"Expected-parse JSON not present: {path}")
    with open(path) as f:
        return json.load(f)


# -------------------------------------------------------------------------
# Helper-function unit tests
# -------------------------------------------------------------------------


class TestAttrHelpers:
    def test_attr_str_returns_value(self, stub_root):
        assert _attr_str(stub_root, "ticId") == "12345678"

    def test_attr_str_returns_none_for_missing(self, stub_root):
        assert _attr_str(stub_root, "nonexistent") is None

    def test_attr_str_returns_none_for_none_element(self):
        assert _attr_str(None, "anything") is None

    def test_attr_int_parses_integer(self, stub_root):
        assert _attr_int(stub_root, "ticId") == 12345678

    def test_attr_int_returns_none_for_missing(self, stub_root):
        assert _attr_int(stub_root, "nonexistent") is None

    def test_attr_float_parses_value(self, stub_root):
        teff = stub_root.find("{http://www.nasa.gov/2018/TESS/DV}effectiveTemp")
        assert _attr_float(teff, "value") == pytest.approx(5500.0)

    def test_attr_float_returns_none_for_missing_attribute(self, stub_root):
        teff = stub_root.find("{http://www.nasa.gov/2018/TESS/DV}effectiveTemp")
        assert _attr_float(teff, "nonexistent") is None

    def test_attr_float_returns_none_for_unparseable(self, stub_root):
        # Construct an element with a non-numeric value
        elem = ET.Element("x", attrib={"value": "not_a_number"})
        assert _attr_float(elem, "value") is None

    def test_attr_bool_handles_true_and_false(self):
        elem_true = ET.Element("x", attrib={"flag": "true"})
        elem_false = ET.Element("x", attrib={"flag": "false"})
        assert _attr_bool(elem_true, "flag") is True
        assert _attr_bool(elem_false, "flag") is False

    def test_attr_bool_returns_none_for_missing(self):
        elem = ET.Element("x")
        assert _attr_bool(elem, "missing") is None


class TestValueOverUncertainty:
    def test_normal_case(self):
        elem = ET.Element("x", attrib={"value": "4.0", "uncertainty": "2.0"})
        assert _value_over_uncertainty(elem) == pytest.approx(2.0)

    def test_none_element(self):
        assert _value_over_uncertainty(None) is None

    def test_zero_uncertainty(self):
        elem = ET.Element("x", attrib={"value": "4.0", "uncertainty": "0.0"})
        assert _value_over_uncertainty(elem) is None

    def test_missing_uncertainty(self):
        elem = ET.Element("x", attrib={"value": "4.0"})
        assert _value_over_uncertainty(elem) is None


class TestSectorsBitmask:
    def test_decode_single_sector(self):
        # Sector 1 only
        bitmask = "0" * 63 + "1"
        assert _decode_sectors_bitmask(bitmask) == [1]

    def test_decode_multiple_sectors(self):
        # Sectors 1, 2, 4 (binary 1011)
        bitmask = "0" * 60 + "1011"
        assert _decode_sectors_bitmask(bitmask) == [1, 2, 4]

    def test_decode_empty_string(self):
        assert _decode_sectors_bitmask("") == []

    def test_decode_none(self):
        assert _decode_sectors_bitmask(None) == []

    def test_decode_invalid_chars_returns_empty(self):
        assert _decode_sectors_bitmask("abc123") == []


# -------------------------------------------------------------------------
# Smoke test: parse the committed fixture and compare to expected JSON
# -------------------------------------------------------------------------


class TestParseFixture:
    def test_fixture_yields_expected_number_of_tces(self, fixture_xml):
        rows = parse_dv_xml(fixture_xml)
        # TOI-700 has 3 confirmed planets
        assert len(rows) == 3

    def test_fixture_yields_correct_tic_id(self, fixture_xml):
        rows = parse_dv_xml(fixture_xml)
        for row in rows:
            assert row["tic_id"] == 307210830

    def test_fixture_has_all_planet_numbers(self, fixture_xml):
        rows = parse_dv_xml(fixture_xml)
        planet_numbers = sorted(r["planet_number"] for r in rows)
        assert planet_numbers == [1, 2, 3]

    def test_fixture_full_convergence_is_bool(self, fixture_xml):
        rows = parse_dv_xml(fixture_xml)
        for row in rows:
            # full_convergence may be True or False but must be bool
            assert isinstance(row["full_convergence"], bool)

    def test_fixture_matches_expected_json(self, fixture_xml, expected_parse):
        """The big regression-protection test.

        Compares the parser's output against a frozen expected JSON.
        Any unintentional change to the parser's output schema or
        values will fail this test.
        """
        rows = parse_dv_xml(fixture_xml)

        # Strip provenance fields that change run-to-run.
        volatile = {"parser_version", "parsed_at"}
        clean_rows = [{k: v for k, v in row.items() if k not in volatile} for row in rows]

        assert len(clean_rows) == len(expected_parse["rows"])

        for actual, expected in zip(clean_rows, expected_parse["rows"], strict=True):
            _assert_rows_equal(actual, expected)


def _assert_rows_equal(actual: dict, expected: dict) -> None:
    """Compare two row dicts. NaN-aware on floats; strict on everything else."""
    assert set(actual.keys()) == set(expected.keys()), (
        f"Column set mismatch.\n"
        f"  Actual only: {set(actual.keys()) - set(expected.keys())}\n"
        f"  Expected only: {set(expected.keys()) - set(actual.keys())}"
    )
    for key in actual:
        a, e = actual[key], expected[key]
        if isinstance(a, float) and isinstance(e, float):
            if math.isnan(a) and math.isnan(e):
                continue
            assert a == pytest.approx(e, rel=1e-9), f"{key}: {a} != {e}"
        else:
            assert a == e, f"{key}: {a!r} != {e!r}"


# -------------------------------------------------------------------------
# parse_sector: end-to-end on a directory containing the fixture
# -------------------------------------------------------------------------


class TestParseSector:
    def test_writes_parquet(self, fixture_xml, tmp_path):
        """Parsing a directory with one XML produces a Parquet file."""
        # Stage the fixture in a temp directory
        staged = tmp_path / "input"
        staged.mkdir()
        (staged / "test.xml").write_bytes(fixture_xml.read_bytes())

        output = tmp_path / "tces.parquet"
        counts = parse_sector(staged, output)

        assert output.exists()
        assert counts["files_total"] == 1
        assert counts["files_ok"] == 1
        assert counts["files_failed"] == 0
        assert counts["tces_extracted"] == 3

    def test_handles_malformed_xml(self, tmp_path):
        """One bad file doesn't crash the run."""
        staged = tmp_path / "input"
        staged.mkdir()
        (staged / "bad.xml").write_text("<not-valid-xml>")

        error_log = tmp_path / "errors.jsonl"
        counts = parse_sector(staged, tmp_path / "out.parquet", error_log)

        assert counts["files_total"] == 1
        assert counts["files_ok"] == 0
        assert counts["files_failed"] == 1
        assert error_log.exists()
        # The error log should contain one entry
        lines = error_log.read_text().strip().split("\n")
        assert len(lines) == 1
        err = json.loads(lines[0])
        assert err["level"] == "file"
        assert err["path"].endswith("bad.xml")
