"""Collapse a grouped (annotated, per-sector) TCE table to one row per signal,
producing a dashboard-ready table.

Strategy: for each signal, take the row of its PEAK-anomaly-score sector as the
representative (you review the signal at its most anomalous detection),
preserving ALL columns. Then overlay:
  - flags combined with the 'any' policy across the signal's sectors, so a
    contaminant flagged in ANY sector stays flagged (flags-not-cuts across
    sectors);
  - anomaly_score = max across sectors (the weirdest detection);
  - n_sectors, sectors_list = the full multi-sector span.

Column names are preserved exactly (no aggregation suffixes) so the dashboard
consumes the output unchanged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Flags OR-ed across a signal's sectors (any-policy).
FLAG_COLS_DEFAULT = [
    "any_diagnostic_flag",
    "flag_suspected_eb", "flag_no_convergence", "flag_invalid_odd_even",
    "flag_background_eb", "flag_centroid_offset", "flag_matching_period",
    "flag_large_odd_even", "flag_low_snr",
    "flag_prsa_eb", "flag_kostov_eb", "flag_oddo_eb", "flag_calnet_eb",
    "flag_catalog_eb", "flag_implausible_metrics",
]


def collapse_to_signals(
    df: pd.DataFrame,
    signal_col: str = "signal_id",
    score_col: str = "anomaly_score",
    sector_col: str = "sector",
    flag_cols: list[str] | None = None,
) -> pd.DataFrame:
    """One row per signal: peak-anomaly representative + any-policy flags."""
    if signal_col not in df.columns:
        raise KeyError(f"missing {signal_col!r}; run group_signals first")
    flag_cols = [c for c in (flag_cols or FLAG_COLS_DEFAULT) if c in df.columns]

    work = df.copy()
    has_score = score_col in work.columns
    if has_score:
        # representative = the max-anomaly-score row per signal
        work["_score_fill"] = pd.to_numeric(work[score_col], errors="coerce").fillna(-np.inf)
        idx = work.groupby(signal_col)["_score_fill"].idxmax()
    else:
        # no score -> first row per signal
        idx = work.groupby(signal_col).head(1).index
    rep = work.loc[idx].copy()
    rep = rep.set_index(signal_col, drop=False)

    # Per-signal aggregates over the FULL group (not just the representative row).
    grp = df.groupby(signal_col)

    # any-policy flags
    for fc in flag_cols:
        anyfired = grp[fc].apply(lambda s: bool(s.fillna(False).astype(bool).any()))
        rep[fc] = rep.index.map(anyfired)
        # transparency: fraction of sectors the flag fired in
        frac = grp[fc].apply(lambda s: float(s.fillna(False).astype(bool).mean()))
        rep[f"{fc}_firedfrac"] = rep.index.map(frac)

    # max anomaly score across sectors
    if has_score:
        smax = grp[score_col].max()
        rep[score_col] = rep.index.map(smax)

    # full multi-sector span
    def _sec_list(s):
        vals = sorted(int(x) for x in pd.to_numeric(s, errors="coerce").dropna().unique())
        return ",".join(str(x) for x in vals)
    rep["sectors_list"] = rep.index.map(grp[sector_col].apply(_sec_list))
    rep["n_sectors"] = rep.index.map(grp[sector_col].nunique())
    rep["is_multisector"] = rep["n_sectors"] > 1

    rep = rep.drop(columns=["_score_fill"], errors="ignore").reset_index(drop=True)
    return rep


if __name__ == "__main__":
    import sys
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else inp.replace(".parquet", "_collapsed.parquet")
    df = pd.read_parquet(inp)
    signals = collapse_to_signals(df)
    print(f"{len(df):,} TCEs -> {len(signals):,} signals")
    signals.to_parquet(out, index=False)
    print(f"saved -> {out}")
