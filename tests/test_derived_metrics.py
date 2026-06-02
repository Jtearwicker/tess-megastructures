"""Tests for tess_megastructures.annotate.derived_metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tess_megastructures.annotate.derived_metrics import (
    add_derived_metrics,
    add_ghost_diagnostic_ratio,
    add_matching_period_signals,
    add_odd_even_depth_sig,
    add_reduced_chi_square,
)


class TestReducedChiSquare:
    def test_basic(self):
        df = pd.DataFrame({"model_chi_square": [220.0], "model_degrees_of_freedom": [100.0]})
        out = add_reduced_chi_square(df)
        assert out["model_chi_square_reduced"].iloc[0] == 2.2

    def test_zero_dof_is_nan(self):
        df = pd.DataFrame({"model_chi_square": [100.0], "model_degrees_of_freedom": [0.0]})
        out = add_reduced_chi_square(df)
        assert pd.isna(out["model_chi_square_reduced"].iloc[0])

    def test_missing_columns_is_nan(self):
        df = pd.DataFrame({"tic_id": [1]})
        out = add_reduced_chi_square(df)
        assert pd.isna(out["model_chi_square_reduced"].iloc[0])


class TestOddEvenDepthSig:
    def test_basic_sqrt(self):
        df = pd.DataFrame({"odd_even_depth_statistic": [100.0]})
        out = add_odd_even_depth_sig(df)
        assert out["odd_even_depth_sig"].iloc[0] == 10.0

    def test_negative_is_nan(self):
        df = pd.DataFrame({"odd_even_depth_statistic": [-5.0]})
        out = add_odd_even_depth_sig(df)
        assert pd.isna(out["odd_even_depth_sig"].iloc[0])

    def test_missing_column_is_nan(self):
        df = pd.DataFrame({"tic_id": [1]})
        out = add_odd_even_depth_sig(df)
        assert pd.isna(out["odd_even_depth_sig"].iloc[0])


class TestGhostDiagnosticRatio:
    def test_basic_ratio(self):
        df = pd.DataFrame({"ghost_core_correlation": [2.0], "ghost_halo_correlation": [1.0]})
        out = add_ghost_diagnostic_ratio(df)
        assert out["ghost_diagnostic_ratio"].iloc[0] == 2.0

    def test_zero_halo_is_nan(self):
        df = pd.DataFrame({"ghost_core_correlation": [1.0], "ghost_halo_correlation": [0.0]})
        out = add_ghost_diagnostic_ratio(df)
        assert pd.isna(out["ghost_diagnostic_ratio"].iloc[0])


class TestMatchingPeriodSignals:
    def test_matching_periods_flagged(self):
        # Same TIC, two periods within 0.01 d -> both flagged
        df = pd.DataFrame(
            {
                "tic_id": [3, 3],
                "planet_number": [1, 2],
                "orbital_period_days": [2.5000, 2.5005],
            }
        )
        out = add_matching_period_signals(df)
        assert list(out["matching_period_signals"]) == [True, True]

    def test_distinct_periods_not_flagged(self):
        # Same TIC, well-separated periods -> not flagged
        df = pd.DataFrame(
            {
                "tic_id": [3, 3],
                "planet_number": [1, 2],
                "orbital_period_days": [2.5, 8.0],
            }
        )
        out = add_matching_period_signals(df)
        assert list(out["matching_period_signals"]) == [False, False]

    def test_single_tce_not_flagged(self):
        df = pd.DataFrame({"tic_id": [1], "planet_number": [1], "orbital_period_days": [5.0]})
        out = add_matching_period_signals(df)
        assert not out["matching_period_signals"].iloc[0]

    def test_different_tics_not_matched(self):
        # Same period but different TICs -> not matched (per-TIC only)
        df = pd.DataFrame(
            {
                "tic_id": [1, 2],
                "planet_number": [1, 1],
                "orbital_period_days": [5.0, 5.0],
            }
        )
        out = add_matching_period_signals(df)
        assert list(out["matching_period_signals"]) == [False, False]

    def test_nan_period_ignored(self):
        df = pd.DataFrame(
            {
                "tic_id": [3, 3],
                "planet_number": [1, 2],
                "orbital_period_days": [2.5, np.nan],
            }
        )
        out = add_matching_period_signals(df)
        # Only one valid period -> no match
        assert list(out["matching_period_signals"]) == [False, False]

    def test_custom_tolerance(self):
        df = pd.DataFrame(
            {
                "tic_id": [3, 3],
                "planet_number": [1, 2],
                "orbital_period_days": [2.50, 2.55],
            }
        )
        # Default 0.01 -> not matched; 0.1 -> matched
        assert not add_matching_period_signals(df)["matching_period_signals"].any()
        assert add_matching_period_signals(df, tol_days=0.1)["matching_period_signals"].all()


class TestAddDerivedMetrics:
    def test_all_columns_added(self):
        df = pd.DataFrame(
            {
                "tic_id": [1],
                "planet_number": [1],
                "orbital_period_days": [5.0],
                "model_chi_square": [150.0],
                "model_degrees_of_freedom": [100.0],
                "odd_even_depth_statistic": [100.0],
                "ghost_core_correlation": [2.0],
                "ghost_halo_correlation": [1.0],
            }
        )
        out = add_derived_metrics(df)
        for col in [
            "model_chi_square_reduced",
            "odd_even_depth_sig",
            "ghost_diagnostic_ratio",
            "matching_period_signals",
        ]:
            assert col in out.columns

    def test_rows_never_dropped(self):
        df = pd.DataFrame(
            {
                "tic_id": [1, 2, 3],
                "planet_number": [1, 1, 1],
                "orbital_period_days": [1.0, 2.0, 3.0],
            }
        )
        out = add_derived_metrics(df)
        assert len(out) == 3
