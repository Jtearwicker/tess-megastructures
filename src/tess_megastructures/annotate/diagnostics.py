"""Diagnostic flags from DV metrics and derived quantities.

Turns raw DV columns and the quantities from ``derived_metrics.py`` into
boolean ``flag_*`` columns. Convention: **True means the TCE is flagged as
suspicious/problematic** for that diagnostic (the opposite polarity from the
``passed_*`` stellar cuts, where True means "good"). This matches how the
flags are used downstream -- candidate selection asks for rows with no
suspicious flags set.

Rows are NEVER dropped. Every flag is added for every row; a flag is False
when the TCE does not trip that diagnostic, and (by configurable policy) for
rows where the metric could not be evaluated (NaN).

This module covers the DV-intrinsic and derived-quantity diagnostics from
Isabel's vetting chain. The catalog cross-match flag (``flag_catalog_binary``
and known-object flags) is handled separately in ``catalog_xmatch.py``, since
it depends on external catalog loaders.

Flags produced
-------------
- flag_suspected_eb       suspected_eclipsing_binary is True (SPOC EB flag)
- flag_no_convergence     transit model fit did not converge
- flag_invalid_odd_even   odd/even significance == -1 (DV sentinel: invalid)
- flag_background_eb      ghost_diagnostic_ratio < ghost_ratio_min (blended EB)
- flag_centroid_offset    signal is off-target by > centroid_offset_max_sigma
- flag_matching_period    TIC has matching-period signals (likely EB)
- flag_large_odd_even     odd_even_depth_sig > odd_even_sig_max (likely EB)
- flag_low_snr            model_fit_snr < snr_min
- annotation_low_rchisq   model_chi_square_reduced < reduced_chisq_min
                          (well-fit by transit model; ANNOTATION not a flag --
                          does not gate survivor selection, per Vishal 2026-06)
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# Default thresholds -- these are Isabel's inherited values. They are
# placeholders pending science calibration and should be supplied via config
# in production. Documented here so the module has sane standalone defaults.
DEFAULT_THRESHOLDS = {
    "ghost_ratio_min": 1.0,  # ratio < this -> background/blended EB
    "centroid_offset_max_sigma": 3.0,  # offset > this (both apertures) -> off-target
    "odd_even_sig_max": 35.0,  # odd_even_depth_sig > this -> likely EB
    "snr_min": 10.0,  # model_fit_snr < this -> low S/N
    "reduced_chisq_min": 1.1,  # rchisq < this -> well-fit (less anomalous)
    "odd_even_invalid_sentinel": -1,  # odd_even significance == this -> invalid
}


def _na_false(series: pd.Series) -> pd.Series:
    """Coerce a boolean-ish series to plain bool with NaN -> False."""
    return series.fillna(False).astype(bool)


def add_diagnostic_flags(
    df: pd.DataFrame,
    thresholds: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Add boolean ``flag_*`` columns (True = suspicious) for each diagnostic.

    Parameters
    ----------
    df : DataFrame
        TCE table that already has derived metrics applied
        (``model_chi_square_reduced``, ``odd_even_depth_sig``,
        ``ghost_diagnostic_ratio``, ``matching_period_signals``).
    thresholds : dict, optional
        Diagnostic thresholds; falls back to ``DEFAULT_THRESHOLDS`` for any
        key not supplied.

    Returns
    -------
    DataFrame
        Input with ``flag_*`` columns added. Rows never dropped.
    """
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    out = df.copy()

    # --- SPOC suspected eclipsing binary
    if "suspected_eclipsing_binary" in out.columns:
        out["flag_suspected_eb"] = _na_false(out["suspected_eclipsing_binary"])
    else:
        out["flag_suspected_eb"] = False

    # --- transit model did not converge
    # Flag only on explicit False; missing data (NaN) is not treated as a
    # failure (we cannot conclude non-convergence from absence of the field).
    if "full_convergence" in out.columns:
        out["flag_no_convergence"] = out["full_convergence"] == False  # noqa: E712
    else:
        out["flag_no_convergence"] = False

    # --- invalid odd/even significance (DV sentinel of -1)
    if "odd_even_depth_significance" in out.columns:
        sentinel = t["odd_even_invalid_sentinel"]
        out["flag_invalid_odd_even"] = _na_false(out["odd_even_depth_significance"] == sentinel)
    else:
        out["flag_invalid_odd_even"] = False

    # --- background/blended EB via ghost diagnostic (ratio < min)
    if "ghost_diagnostic_ratio" in out.columns:
        out["flag_background_eb"] = _na_false(out["ghost_diagnostic_ratio"] < t["ghost_ratio_min"])
    else:
        out["flag_background_eb"] = False

    # --- difference-image centroid offset (off-target source)
    # Isabel kept a TCE if EITHER aperture offset was < threshold; so a TCE
    # is "off-target" only when BOTH offsets are >= threshold. We flag only
    # when there is positive evidence of an offset: at least one offset is
    # present AND no present offset is on-target. If both offsets are
    # missing, we cannot conclude off-target -> not flagged.
    tic_col = "ms_tic_centroid_offset_sigma"
    ctrl_col = "ms_control_centroid_offset_sigma"
    if tic_col in out.columns and ctrl_col in out.columns:
        thr = t["centroid_offset_max_sigma"]
        tic_on = out[tic_col] < thr  # NaN -> False
        ctrl_on = out[ctrl_col] < thr  # NaN -> False
        any_present = out[tic_col].notna() | out[ctrl_col].notna()
        any_on_target = tic_on | ctrl_on
        # off-target = at least one offset present, and none is on-target
        out["flag_centroid_offset"] = any_present & ~any_on_target
    else:
        out["flag_centroid_offset"] = False

    # --- matching-period signals (likely missed binary)
    if "matching_period_signals" in out.columns:
        out["flag_matching_period"] = _na_false(out["matching_period_signals"])
    else:
        out["flag_matching_period"] = False

    # --- large odd/even depth difference (likely EB)
    if "odd_even_depth_sig" in out.columns:
        out["flag_large_odd_even"] = _na_false(out["odd_even_depth_sig"] > t["odd_even_sig_max"])
    else:
        out["flag_large_odd_even"] = False

    # --- low S/N
    if "model_fit_snr" in out.columns:
        out["flag_low_snr"] = _na_false(out["model_fit_snr"] < t["snr_min"])
    else:
        out["flag_low_snr"] = False

    # --- low reduced chi-square (well-fit by transit model -> less anomalous)
    # NOTE: annotation, NOT a flag. Per Vishal (2026-06), rchisq must not gate
    # candidate selection -- a clean transit fit is recorded but does not
    # exclude a TCE from the survivor set. Hence the annotation_ prefix and
    # absence from DIAGNOSTIC_FLAG_COLUMNS.
    if "model_chi_square_reduced" in out.columns:
        out["annotation_low_rchisq"] = _na_false(
            out["model_chi_square_reduced"] < t["reduced_chisq_min"]
        )
    else:
        out["annotation_low_rchisq"] = False

    return out


# The canonical list of flag columns this module produces (excluding the
# catalog cross-match flag, which lives in catalog_xmatch.py).
DIAGNOSTIC_FLAG_COLUMNS = [
    "flag_suspected_eb",
    "flag_no_convergence",
    "flag_invalid_odd_even",
    "flag_background_eb",
    "flag_centroid_offset",
    "flag_matching_period",
    "flag_large_odd_even",
    "flag_low_snr",
]


def add_any_flag_column(
    df: pd.DataFrame,
    flag_columns: list[str] | None = None,
    out_column: str = "any_diagnostic_flag",
) -> pd.DataFrame:
    """Add a convenience column: True if ANY diagnostic flag is set.

    Useful for the "show me everything not flagged" query. Only considers
    flag columns that are actually present.
    """
    out = df.copy()
    cols = flag_columns or DIAGNOSTIC_FLAG_COLUMNS
    present = [c for c in cols if c in out.columns]
    if present:
        out[out_column] = out[present].any(axis=1)
    else:
        out[out_column] = False
    return out
