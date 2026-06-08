"""Tests for tess_megastructures.annotate.diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tess_megastructures.annotate.derived_metrics import add_derived_metrics
from tess_megastructures.annotate.diagnostics import (
    DIAGNOSTIC_FLAG_COLUMNS,
    add_any_flag_column,
    add_diagnostic_flags,
)


def _clean_row() -> dict:
    """A TCE that should trip NO diagnostic flags."""
    return {
        "tic_id": 1,
        "planet_number": 1,
        "orbital_period_days": 5.0,
        "model_chi_square": 220.0,
        "model_degrees_of_freedom": 100.0,  # rchisq 2.2 (>1.1, not flagged)
        "odd_even_depth_statistic": 100.0,  # sig 10 (<35)
        "odd_even_depth_significance": 5.0,  # valid
        "ghost_core_correlation": 2.0,
        "ghost_halo_correlation": 1.0,  # ratio 2.0 (>1)
        "ms_tic_centroid_offset_sigma": 1.0,  # on-target
        "ms_control_centroid_offset_sigma": 1.0,
        "model_fit_snr": 50.0,  # >20
        "full_convergence": True,
        "suspected_eclipsing_binary": False,
    }


class TestIndividualFlags:
    def _flags(self, overrides: dict) -> pd.Series:
        row = {**_clean_row(), **overrides}
        df = add_derived_metrics(pd.DataFrame([row]))
        return add_diagnostic_flags(df).iloc[0]

    def test_clean_row_trips_nothing(self):
        f = self._flags({})
        for col in DIAGNOSTIC_FLAG_COLUMNS:
            assert not bool(f[col]), f"{col} should be False for a clean row"

    def test_suspected_eb(self):
        assert bool(self._flags({"suspected_eclipsing_binary": True})["flag_suspected_eb"])

    def test_no_convergence(self):
        assert bool(self._flags({"full_convergence": False})["flag_no_convergence"])

    def test_no_convergence_nan_not_flagged(self):
        assert not bool(self._flags({"full_convergence": np.nan})["flag_no_convergence"])

    def test_invalid_odd_even(self):
        assert bool(self._flags({"odd_even_depth_significance": -1})["flag_invalid_odd_even"])

    def test_background_eb(self):
        # ghost ratio < 1
        f = self._flags({"ghost_core_correlation": 0.5, "ghost_halo_correlation": 1.0})
        assert bool(f["flag_background_eb"])

    def test_large_odd_even(self):
        # sig = sqrt(2025) = 45 > 35
        assert bool(self._flags({"odd_even_depth_statistic": 2025.0})["flag_large_odd_even"])

    def test_low_snr(self):
        assert bool(self._flags({"model_fit_snr": 5.0})["flag_low_snr"])

    def test_low_rchisq(self):
        # rchisq = 50/100 = 0.5 < 1.1
        assert bool(self._flags({"model_chi_square": 50.0})["annotation_low_rchisq"])


class TestCentroidOffsetFlag:
    """The centroid OR-logic and its NaN handling are the subtlest part."""

    def _flag(self, tic, ctrl) -> bool:
        df = pd.DataFrame(
            [
                {
                    "ms_tic_centroid_offset_sigma": tic,
                    "ms_control_centroid_offset_sigma": ctrl,
                }
            ]
        )
        return bool(add_diagnostic_flags(df)["flag_centroid_offset"].iloc[0])

    def test_both_on_target_not_flagged(self):
        assert self._flag(1.0, 1.0) is False

    def test_both_off_target_flagged(self):
        assert self._flag(5.0, 4.0) is True

    def test_one_on_one_off_not_flagged(self):
        # Isabel kept if EITHER aperture was on-target
        assert self._flag(5.0, 1.0) is False

    def test_one_present_off_target_flagged(self):
        assert self._flag(5.0, np.nan) is True

    def test_one_present_on_target_not_flagged(self):
        assert self._flag(1.0, np.nan) is False

    def test_both_missing_not_flagged(self):
        # Regression: missing data must NOT be read as off-target
        assert self._flag(np.nan, np.nan) is False


class TestMatchingPeriodFlag:
    def test_matching_period_flagged(self):
        df = pd.DataFrame(
            {
                "tic_id": [3, 3],
                "planet_number": [1, 2],
                "orbital_period_days": [2.5000, 2.5005],
            }
        )
        df = add_derived_metrics(df)
        out = add_diagnostic_flags(df)
        assert list(out["flag_matching_period"]) == [True, True]


class TestAllNaNRobustness:
    def test_all_nan_row_no_flags(self):
        df = pd.DataFrame(
            [
                {
                    "tic_id": 1,
                    "planet_number": 1,
                    "orbital_period_days": np.nan,
                    "model_chi_square": np.nan,
                    "model_degrees_of_freedom": np.nan,
                    "odd_even_depth_statistic": np.nan,
                    "odd_even_depth_significance": np.nan,
                    "ghost_core_correlation": np.nan,
                    "ghost_halo_correlation": np.nan,
                    "ms_tic_centroid_offset_sigma": np.nan,
                    "ms_control_centroid_offset_sigma": np.nan,
                    "model_fit_snr": np.nan,
                    "full_convergence": np.nan,
                    "suspected_eclipsing_binary": np.nan,
                }
            ]
        )
        df = add_derived_metrics(df)
        out = add_diagnostic_flags(df)
        for col in DIAGNOSTIC_FLAG_COLUMNS:
            assert not bool(out[col].iloc[0]), f"{col} should be False for all-NaN row"

    def test_flags_are_bool_dtype(self):
        df = add_derived_metrics(pd.DataFrame([_clean_row()]))
        out = add_diagnostic_flags(df)
        for col in DIAGNOSTIC_FLAG_COLUMNS:
            assert out[col].dtype == bool

    def test_missing_columns_no_crash(self):
        df = pd.DataFrame({"tic_id": [1, 2], "planet_number": [1, 1]})
        df = add_derived_metrics(df)
        out = add_diagnostic_flags(df)
        assert len(out) == 2
        for col in DIAGNOSTIC_FLAG_COLUMNS:
            assert col in out.columns


class TestConfigurableThresholds:
    def test_custom_snr_threshold(self):
        row = {**_clean_row(), "model_fit_snr": 30.0}
        df = add_derived_metrics(pd.DataFrame([row]))
        # default snr_min 20 -> 30 not flagged; raise to 40 -> flagged
        assert not bool(add_diagnostic_flags(df)["flag_low_snr"].iloc[0])
        assert bool(add_diagnostic_flags(df, {"snr_min": 40.0})["flag_low_snr"].iloc[0])


class TestAnyFlagColumn:
    def test_any_flag_true_when_one_set(self):
        row = {**_clean_row(), "model_fit_snr": 5.0}  # trips low_snr
        df = add_derived_metrics(pd.DataFrame([row]))
        out = add_any_flag_column(add_diagnostic_flags(df))
        assert bool(out["any_diagnostic_flag"].iloc[0])

    def test_any_flag_false_for_clean(self):
        df = add_derived_metrics(pd.DataFrame([_clean_row()]))
        out = add_any_flag_column(add_diagnostic_flags(df))
        assert not bool(out["any_diagnostic_flag"].iloc[0])

    def test_rows_never_dropped(self):
        df = add_derived_metrics(pd.DataFrame([_clean_row(), {**_clean_row(), "tic_id": 2}]))
        out = add_any_flag_column(add_diagnostic_flags(df))
        assert len(out) == 2
