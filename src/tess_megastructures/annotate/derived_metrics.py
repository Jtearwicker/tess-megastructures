"""Derived diagnostic metrics from parsed DV columns.

Computes the quantities Isabel's vetting pipeline derived from raw DV
metrics, plus the per-TIC matching-period heuristic. These are pure
functions of the parsed TCE table; they add columns and never drop rows.

Derived quantities
------------------
- ``model_chi_square_reduced`` = model_chi_square / model_degrees_of_freedom
- ``odd_even_depth_sig``       = sqrt(odd_even_depth_statistic)
- ``ghost_diagnostic_ratio``   = ghost_core_correlation / ghost_halo_correlation
- ``matching_period_signals``  = True where a TIC has >=2 TCEs whose orbital
  periods agree within a tolerance (Isabel's "missed binary" heuristic)

These feed ``diagnostics.py``, which turns them (plus raw DV columns) into
boolean ``flag_*`` columns at configurable thresholds.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default tolerance (days) for the matching-period heuristic. Isabel used
# 0.01 d. Configurable via the caller.
DEFAULT_PERIOD_MATCH_TOL_DAYS = 0.01


def add_reduced_chi_square(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``model_chi_square_reduced`` = model_chi_square / dof.

    Division-by-zero or missing inputs yield NaN (not an exception), so the
    column is always present and downstream flagging treats NaN as
    "could not evaluate".
    """
    out = df.copy()
    if {"model_chi_square", "model_degrees_of_freedom"}.issubset(out.columns):
        dof = out["model_degrees_of_freedom"].replace(0, np.nan)
        out["model_chi_square_reduced"] = out["model_chi_square"] / dof
    else:
        logger.warning(
            "model_chi_square / model_degrees_of_freedom missing; "
            "model_chi_square_reduced set to NaN"
        )
        out["model_chi_square_reduced"] = np.nan
    return out


def add_odd_even_depth_sig(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``odd_even_depth_sig`` = sqrt(odd_even_depth_statistic).

    Negative or missing statistics yield NaN. Note this is distinct from the
    parser's ``odd_even_depth_significance`` column, which is a separate DV
    field used (with its -1 sentinel) for the validity check.
    """
    out = df.copy()
    if "odd_even_depth_statistic" in out.columns:
        stat = out["odd_even_depth_statistic"]
        # sqrt of negatives -> NaN; guard explicitly to avoid warnings
        safe = stat.where(stat >= 0, np.nan)
        out["odd_even_depth_sig"] = np.sqrt(safe)
    else:
        logger.warning("odd_even_depth_statistic missing; odd_even_depth_sig set to NaN")
        out["odd_even_depth_sig"] = np.nan
    return out


def add_ghost_diagnostic_ratio(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``ghost_diagnostic_ratio`` = core / halo aperture correlation.

    A ratio < 1 indicates the signal correlates more with the halo than the
    core aperture -- a blended/background eclipsing-binary signature. Missing
    inputs or halo == 0 yield NaN.
    """
    out = df.copy()
    if {"ghost_core_correlation", "ghost_halo_correlation"}.issubset(out.columns):
        halo = out["ghost_halo_correlation"].replace(0, np.nan)
        out["ghost_diagnostic_ratio"] = out["ghost_core_correlation"] / halo
    else:
        logger.warning(
            "ghost_core_correlation / ghost_halo_correlation missing; "
            "ghost_diagnostic_ratio set to NaN"
        )
        out["ghost_diagnostic_ratio"] = np.nan
    return out


def add_matching_period_signals(
    df: pd.DataFrame,
    tol_days: float = DEFAULT_PERIOD_MATCH_TOL_DAYS,
) -> pd.DataFrame:
    """Flag TICs with >=2 TCEs whose orbital periods agree within tol_days.

    This is Isabel's "missed binary" heuristic: when multiple TCEs on the
    same target share a period, the signal is typically an eclipsing binary
    that produced multiple threshold crossings rather than distinct planets.

    Implemented with a per-TIC groupby (O(n log n) within each TIC) rather
    than the original O(n^2) all-pairs loop, so it scales to the full TCE
    population. The boolean is set on every TCE of a flagged TIC.

    Rows with NaN period are ignored for matching (cannot match).
    """
    out = df.copy()
    out["matching_period_signals"] = False

    if not {"tic_id", "orbital_period_days"}.issubset(out.columns):
        logger.warning("tic_id / orbital_period_days missing; matching_period_signals all False")
        return out

    flagged_tics: list = []
    for tic_id, group in out.groupby("tic_id"):
        periods = group["orbital_period_days"].dropna().sort_values().to_numpy()
        if periods.size < 2:
            continue
        # Sorted adjacent differences: if any pair is within tol, the TIC has
        # at least two matching-period signals.
        if np.any(np.diff(periods) < tol_days):
            flagged_tics.append(tic_id)

    if flagged_tics:
        out.loc[out["tic_id"].isin(flagged_tics), "matching_period_signals"] = True
    return out


def add_derived_metrics(
    df: pd.DataFrame,
    period_match_tol_days: float = DEFAULT_PERIOD_MATCH_TOL_DAYS,
) -> pd.DataFrame:
    """Add all derived diagnostic quantities in one pass.

    Order is irrelevant (each is independent), but they are applied
    sequentially for clarity. Never drops rows.
    """
    out = add_reduced_chi_square(df)
    out = add_odd_even_depth_sig(out)
    out = add_ghost_diagnostic_ratio(out)
    out = add_matching_period_signals(out, tol_days=period_match_tol_days)
    return out
