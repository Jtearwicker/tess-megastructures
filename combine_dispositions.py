"""
Cross-sector disposition combination for grouped target-signals.

Runs AFTER group_signals.py has assigned signal_id. Takes the per-sector flags
(the same diagnostic flags the single-sector pipeline computes) and combines them
to a per-SIGNAL disposition, using an explicit, configurable policy.

DESIGN PRINCIPLE (flags-not-cuts, surfaced not buried)
------------------------------------------------------
The combination POLICY is a scientific choice, so it is an explicit parameter, not
a hidden default. Three policies are provided; none of them silently drops data.

  flag_policy='any'  (recommended, matches flags-not-cuts):
      A signal carries a flag if it fired in ANY sector. Rationale: if an EB was
      caught by the odd/even test in even one sector, it IS an EB -- a clean sector
      shouldn't launder it. Most conservative about contamination.

  flag_policy='all':
      A signal carries a flag only if it fired in EVERY sector it was seen in.
      More permissive -- keeps candidates that look bad in one sector but clean in
      others. Higher completeness, lower purity.

  flag_policy='majority':
      Flag if it fired in >50% of the signal's sectors.

For continuous quantities (SNR, chisq), we also surface the BEST and MEDIAN across
sectors, so a downstream user can see "this signal's strongest detection" vs "its
typical detection" -- multi-sector's actual scientific payoff (more transits ->
higher combined SNR is expressed as max_snr rising with n_sectors).

The combined table is one row per SIGNAL, with per-sector evidence preserved in the
grouped TCE table (nothing is thrown away).
"""
import numpy as np
import pandas as pd


# the boolean diagnostic flags produced per-sector (extend as needed)
DEFAULT_FLAG_COLS = [
    "suspectedEclipsingBinary",
    "catalogBinary",
    "matchingPeriodSignals",
]

# continuous metrics where we want cross-sector best/median
DEFAULT_METRIC_COLS = {
    "modelFitSnr": "max",           # more transits -> higher SNR; best sector matters
    "modelChiSquare_reduced": "median",
    "oddEvenDepth_sig": "max",      # strongest EB signal across sectors
    "GhostDiagnostic_chr": "min",   # most background-like sector
}


def combine_signal_dispositions(
    grouped_df,
    signal_col="signal_id",
    flag_cols=None,
    metric_cols=None,
    flag_policy="any",
):
    """Collapse a grouped (per-sector) TCE table to one row per signal.

    Returns a per-signal DataFrame with:
      - signal_id, ticId, n_sectors, sectors_list
      - each flag combined per `flag_policy` (bool)
      - each metric aggregated per its rule (max/median/min), plus n_sectors
      - flag_fired_fraction_<flag> : in what fraction of sectors each flag fired
        (transparency -- lets you see 'any' vs 'all' disagreement)
    """
    flag_cols = flag_cols or DEFAULT_FLAG_COLS
    metric_cols = metric_cols or DEFAULT_METRIC_COLS
    flag_cols = [c for c in flag_cols if c in grouped_df.columns]
    metric_cols = {k: v for k, v in metric_cols.items() if k in grouped_df.columns}

    recs = []
    for sid, g in grouped_df.groupby(signal_col):
        rec = {
            "signal_id": sid,
            "ticId": g["ticId"].iloc[0],
            "n_sectors": int(g["sector"].nunique()),
            "sectors_list": ",".join(str(x) for x in sorted(g["sector"].dropna().unique())),
        }
        # combine each boolean flag per policy
        for fc in flag_cols:
            fired = g[fc].fillna(False).astype(bool)
            frac = fired.mean()
            rec[f"{fc}_firedfrac"] = frac
            if flag_policy == "any":
                rec[fc] = bool(fired.any())
            elif flag_policy == "all":
                rec[fc] = bool(fired.all())
            elif flag_policy == "majority":
                rec[fc] = bool(frac > 0.5)
            else:
                raise ValueError(f"unknown flag_policy {flag_policy!r}")
        # aggregate continuous metrics
        for mc, how in metric_cols.items():
            vals = pd.to_numeric(g[mc], errors="coerce").dropna()
            if len(vals):
                rec[f"{mc}_{how}"] = getattr(vals, how)()
            else:
                rec[f"{mc}_{how}"] = np.nan
        # carry TOI if any sector had one
        if "toiId" in g.columns:
            tois = g["toiId"].dropna().unique()
            rec["toiId"] = tois[0] if len(tois) else np.nan
        recs.append(rec)

    return pd.DataFrame(recs)


if __name__ == "__main__":
    import sys
    from group_signals import group_target_signals
    df = pd.read_csv(sys.argv[1])
    g = group_target_signals(df)
    policy = sys.argv[2] if len(sys.argv) > 2 else "any"
    combined = combine_signal_dispositions(g, flag_policy=policy)
    print(f"{len(df)} TCEs -> {len(combined)} signals (policy={policy})")
    out = sys.argv[1].replace(".csv", f"_signals_{policy}.csv")
    combined.to_csv(out, index=False)
    print(f"wrote {out}")
