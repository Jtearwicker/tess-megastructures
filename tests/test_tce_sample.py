"""Tests for tess_megastructures.ingest.tce_sample.

Uses synthetic in-memory DataFrames so the tests are self-contained and
do not depend on parsed sector data, MAST downloads, or external catalogs.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tess_megastructures.ingest.tce_sample import (
    aggregate_parsed_sectors,
    apply_cuts,
    build_tce_sample,
    classify_run_type,
    enrich_with_doyle,
)

# -------------------------------------------------------------------------
# Fixtures: synthetic parsed-sector data
# -------------------------------------------------------------------------


def _make_tce_frame(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal TCE DataFrame with the columns the module expects."""
    defaults = {
        "tic_id": 0,
        "planet_number": 1,
        "sector": 36,
        "tess_mag": 10.0,
        "effective_temp": 5500.0,
        "radius": 1.0,
        "log_g": 4.5,
        "n_difference_images": 1,
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


@pytest.fixture
def two_sector_frames(tmp_path):
    """Two parsed-sector Parquet files staged on disk."""
    s36 = _make_tce_frame(
        [
            {"tic_id": 111, "planet_number": 1, "sector": 36},
            {"tic_id": 222, "planet_number": 1, "sector": 36},
        ]
    )
    s37 = _make_tce_frame(
        [
            {"tic_id": 111, "planet_number": 1, "sector": 37},  # same TIC, new sector
            {"tic_id": 333, "planet_number": 1, "sector": 37},
        ]
    )
    p36 = tmp_path / "tce_dv_metrics_s0036.parquet"
    p37 = tmp_path / "tce_dv_metrics_s0037.parquet"
    s36.to_parquet(p36, index=False)
    s37.to_parquet(p37, index=False)
    return [p36, p37]


@pytest.fixture
def basic_config():
    return {
        "version": "v1-test",
        "stellar_cuts": {
            "tmag_min": 6.0,
            "tmag_max": 14.0,
            "log_g_min": 3.5,
            "parallax_over_error_min": 5.0,
            "ruwe_max_for_clean": 1.4,
        },
        "require_valid": ["effective_temp", "radius", "log_g", "tess_mag"],
        "required_for_clean": [
            "passed_tmag_cut",
            "passed_log_g_cut",
            "has_valid_stellar_params",
        ],
    }


# -------------------------------------------------------------------------
# Aggregation
# -------------------------------------------------------------------------


class TestAggregate:
    def test_concatenates_all_rows(self, two_sector_frames):
        df = aggregate_parsed_sectors(two_sector_frames)
        assert len(df) == 4

    def test_preserves_multi_sector_same_tic(self, two_sector_frames):
        df = aggregate_parsed_sectors(two_sector_frames)
        # TIC 111 appears in both sectors -> two rows
        assert (df["tic_id"] == 111).sum() == 2

    def test_empty_input_returns_empty(self):
        df = aggregate_parsed_sectors([])
        assert df.empty


# -------------------------------------------------------------------------
# Run-type classification
# -------------------------------------------------------------------------


class TestRunType:
    def test_single_sector_flagged(self):
        df = _make_tce_frame([{"tic_id": 1, "n_difference_images": 1}])
        out = classify_run_type(df)
        assert out["run_type"].iloc[0] == "single_sector"

    def test_multi_sector_flagged(self):
        df = _make_tce_frame([{"tic_id": 1, "n_difference_images": 5}])
        out = classify_run_type(df)
        assert out["run_type"].iloc[0] == "multi_sector"

    def test_missing_column_defaults_single(self):
        df = pd.DataFrame([{"tic_id": 1, "planet_number": 1}])
        out = classify_run_type(df)
        assert out["run_type"].iloc[0] == "single_sector"


# -------------------------------------------------------------------------
# Doyle enrichment
# -------------------------------------------------------------------------


class TestDoyleEnrichment:
    def test_no_doyle_sets_flag_false(self):
        df = _make_tce_frame([{"tic_id": 111}])
        out = enrich_with_doyle(df, None)
        assert not out["has_doyle_params"].iloc[0]

    def test_match_attaches_params_and_flag(self):
        df = _make_tce_frame([{"tic_id": 111}, {"tic_id": 999}])
        doyle = pd.DataFrame([{"tic_id": 111, "ruwe": 1.1, "parallax_over_error": 20.0}])
        out = enrich_with_doyle(df, doyle)
        # TIC 111 matched, 999 did not
        row_111 = out[out["tic_id"] == 111].iloc[0]
        row_999 = out[out["tic_id"] == 999].iloc[0]
        assert bool(row_111["has_doyle_params"]) is True
        assert bool(row_999["has_doyle_params"]) is False
        assert row_111["doyle_ruwe"] == pytest.approx(1.1)
        # Unmatched row has null Doyle params
        assert pd.isna(row_999["doyle_ruwe"])

    def test_does_not_clobber_dv_params(self):
        # Doyle has a column that would collide without the prefix
        df = _make_tce_frame([{"tic_id": 111, "radius": 1.23}])
        doyle = pd.DataFrame([{"tic_id": 111, "radius": 9.99}])
        out = enrich_with_doyle(df, doyle)
        # DV radius preserved; Doyle radius is under doyle_radius
        assert out["radius"].iloc[0] == pytest.approx(1.23)
        assert out["doyle_radius"].iloc[0] == pytest.approx(9.99)


# -------------------------------------------------------------------------
# Cuts
# -------------------------------------------------------------------------


class TestCuts:
    def test_tmag_cut(self, basic_config):
        df = _make_tce_frame(
            [
                {"tic_id": 1, "tess_mag": 10.0},  # in range
                {"tic_id": 2, "tess_mag": 20.0},  # too faint
                {"tic_id": 3, "tess_mag": 3.0},  # too bright
            ]
        )
        out = apply_cuts(df, basic_config)
        assert list(out["passed_tmag_cut"]) == [True, False, False]

    def test_log_g_cut(self, basic_config):
        df = _make_tce_frame(
            [
                {"tic_id": 1, "log_g": 4.5},  # main sequence
                {"tic_id": 2, "log_g": 2.0},  # giant
            ]
        )
        out = apply_cuts(df, basic_config)
        assert list(out["passed_log_g_cut"]) == [True, False]

    def test_valid_stellar_params(self, basic_config):
        df = _make_tce_frame(
            [
                {"tic_id": 1},  # all present
                {"tic_id": 2, "radius": None},  # missing radius
            ]
        )
        out = apply_cuts(df, basic_config)
        assert bool(out["has_valid_stellar_params"].iloc[0]) is True
        assert bool(out["has_valid_stellar_params"].iloc[1]) is False

    def test_in_clean_sample_is_and_of_required(self, basic_config):
        df = _make_tce_frame(
            [
                {"tic_id": 1, "tess_mag": 10.0, "log_g": 4.5},  # passes all
                {"tic_id": 2, "tess_mag": 20.0, "log_g": 4.5},  # fails tmag
                {"tic_id": 3, "tess_mag": 10.0, "log_g": 2.0},  # fails log_g
            ]
        )
        out = apply_cuts(df, basic_config)
        assert list(out["in_clean_sample"]) == [True, False, False]

    def test_rows_never_dropped(self, basic_config):
        df = _make_tce_frame(
            [{"tic_id": i, "tess_mag": 30.0} for i in range(5)]  # all fail tmag
        )
        out = apply_cuts(df, basic_config)
        # Every row retained even though none pass
        assert len(out) == 5
        assert out["in_clean_sample"].sum() == 0


# -------------------------------------------------------------------------
# End-to-end
# -------------------------------------------------------------------------


class TestBuildTceSample:
    def test_end_to_end_writes_parquet(self, two_sector_frames, basic_config, tmp_path):
        doyle = pd.DataFrame([{"tic_id": 111, "ruwe": 1.1, "parallax_over_error": 20.0}])
        out_path = tmp_path / "tce_sample_v1.parquet"
        df = build_tce_sample(two_sector_frames, basic_config, out_path, doyle=doyle)

        assert out_path.exists()
        assert len(df) == 4  # all TCEs retained
        # Provenance columns present
        assert "tce_sample_version" in df.columns
        assert "built_at" in df.columns
        assert df["tce_sample_version"].iloc[0] == "v1-test"
        # Doyle enrichment applied (TIC 111 in both sectors -> 2 matched rows)
        assert df["has_doyle_params"].sum() == 2

    def test_empty_input_returns_empty(self, basic_config):
        df = build_tce_sample([], basic_config, None)
        assert df.empty
