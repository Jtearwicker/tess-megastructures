"""Integration test: diagnostic flags flow through build_tce_sample().

Confirms that the Subsystem-B wiring (derived metrics + diagnostic flags)
is actually invoked by build_tce_sample and produces the expected flag
columns in the output -- the contract that the build driver relies on.
"""

from __future__ import annotations

import pandas as pd

from tess_megastructures.annotate.diagnostics import DIAGNOSTIC_FLAG_COLUMNS
from tess_megastructures.ingest.tce_sample import build_tce_sample


def _diag_config() -> dict:
    return {
        "version": "v1-test",
        "stellar_cuts": {
            "tmag_min": 6.0,
            "tmag_max": 14.0,
            "log_g_min": 3.5,
        },
        "require_valid": ["effective_temp", "radius", "log_g", "tess_mag"],
        "required_for_clean": [
            "passed_tmag_cut",
            "passed_log_g_cut",
            "has_valid_stellar_params",
        ],
        "diagnostics": {
            "ghost_ratio_min": 1.0,
            "centroid_offset_max_sigma": 3.0,
            "odd_even_sig_max": 35.0,
            "snr_min": 20.0,
            "reduced_chisq_min": 1.1,
            "odd_even_invalid_sentinel": -1,
            "period_match_tol_days": 0.01,
        },
    }


def _staged_parquet(tmp_path, rows):
    df = pd.DataFrame(rows)
    p = tmp_path / "tce_dv_metrics_s0099.parquet"
    df.to_parquet(p, index=False)
    return [p]


def _clean_row():
    return {
        "tic_id": 1,
        "planet_number": 1,
        "sector": 99,
        "tess_mag": 10.0,
        "effective_temp": 5500.0,
        "radius": 1.0,
        "log_g": 4.5,
        "n_difference_images": 1,
        "orbital_period_days": 5.0,
        "model_chi_square": 220.0,
        "model_degrees_of_freedom": 100.0,
        "odd_even_depth_statistic": 100.0,
        "odd_even_depth_significance": 5.0,
        "ghost_core_correlation": 2.0,
        "ghost_halo_correlation": 1.0,
        "ms_tic_centroid_offset_sigma": 1.0,
        "ms_control_centroid_offset_sigma": 1.0,
        "model_fit_snr": 50.0,
        "full_convergence": True,
        "suspected_eclipsing_binary": False,
    }


class TestDiagnosticsWiredIntoBuild:
    def test_flag_columns_present_in_output(self, tmp_path):
        paths = _staged_parquet(tmp_path, [_clean_row()])
        df = build_tce_sample(paths, _diag_config(), output_path=None, doyle=None)
        for col in DIAGNOSTIC_FLAG_COLUMNS:
            assert col in df.columns, f"{col} missing from build output"
        assert "any_diagnostic_flag" in df.columns

    def test_derived_metric_columns_present(self, tmp_path):
        paths = _staged_parquet(tmp_path, [_clean_row()])
        df = build_tce_sample(paths, _diag_config(), output_path=None, doyle=None)
        for col in [
            "model_chi_square_reduced",
            "odd_even_depth_sig",
            "ghost_diagnostic_ratio",
            "matching_period_signals",
        ]:
            assert col in df.columns

    def test_clean_row_unflagged(self, tmp_path):
        paths = _staged_parquet(tmp_path, [_clean_row()])
        df = build_tce_sample(paths, _diag_config(), output_path=None, doyle=None)
        assert not bool(df["any_diagnostic_flag"].iloc[0])

    def test_junk_row_flagged(self, tmp_path):
        junk = {
            **_clean_row(),
            "tic_id": 2,
            "model_fit_snr": 5.0,  # low SNR
            "full_convergence": False,  # no convergence
            "suspected_eclipsing_binary": True,  # SPOC EB
        }
        paths = _staged_parquet(tmp_path, [junk])
        df = build_tce_sample(paths, _diag_config(), output_path=None, doyle=None)
        assert bool(df["any_diagnostic_flag"].iloc[0])
        assert bool(df["flag_low_snr"].iloc[0])
        assert bool(df["flag_no_convergence"].iloc[0])
        assert bool(df["flag_suspected_eb"].iloc[0])

    def test_rows_never_dropped(self, tmp_path):
        rows = [_clean_row(), {**_clean_row(), "tic_id": 2, "model_fit_snr": 1.0}]
        paths = _staged_parquet(tmp_path, rows)
        df = build_tce_sample(paths, _diag_config(), output_path=None, doyle=None)
        assert len(df) == 2

    def test_thresholds_read_from_config(self, tmp_path):
        # A row with SNR=30: default snr_min 20 -> not flagged; raise to 40 -> flagged
        row = {**_clean_row(), "model_fit_snr": 30.0}
        paths = _staged_parquet(tmp_path, [row])

        cfg_default = _diag_config()
        df1 = build_tce_sample(paths, cfg_default, output_path=None, doyle=None)
        assert not bool(df1["flag_low_snr"].iloc[0])

        cfg_strict = _diag_config()
        cfg_strict["diagnostics"]["snr_min"] = 40.0
        df2 = build_tce_sample(paths, cfg_strict, output_path=None, doyle=None)
        assert bool(df2["flag_low_snr"].iloc[0])
