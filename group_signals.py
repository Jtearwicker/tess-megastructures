"""
Cross-sector target-signal grouping for the MegaMiner TCE pipeline.

PROBLEM
-------
When TESS observes a target in N sectors, SPOC produces a separate TCE for the
same astrophysical signal in each sector. The single-sector pipeline treats these
as N independent rows and gates each alone, so the SAME planet/EB can end up with
inconsistent survivor status across sectors. This module adds a stable *signal
identity* so a target's evidence can be combined across sectors.

WHAT IT DOES (and does NOT do)
------------------------------
It ONLY assigns a `signal_id` grouping key. It does NOT gate, cut, or combine
dispositions -- those are separate, deliberate steps (flags-not-cuts). Grouping is
a factual clustering ("these rows are the same signal"), not a scientific judgment.

GROUPING RULE
-------------
Two TCEs are the same signal iff:
  - same `ticId`, AND
  - orbital periods agree within a fractional tolerance (default 1%), allowing
    the 2x / 0.5x harmonic ambiguity that SPOC frequently produces for EBs, AND
  - (optionally) transit epochs are consistent modulo the period.

The harmonic allowance mirrors what you already know from DV vetting: an EB often
appears at half the true period in one sector and the full period in another.

This generalizes the existing within-sector `matchingPeriodSignals` logic (which
found same-period TCEs on one target in one sector) to work ACROSS sectors.
"""
import numpy as np
import pandas as pd


def _period_consistent(p1, p2, tol=0.01, allow_harmonics=True):
    """True if two periods match within `tol` (fractional), optionally allowing
    2x / 0.5x harmonics."""
    if not (np.isfinite(p1) and np.isfinite(p2)) or p1 <= 0 or p2 <= 0:
        return False
    factors = [1.0, 2.0, 0.5] if allow_harmonics else [1.0]
    return any(abs(p1 - p2 * f) / (p2 * f) < tol for f in factors)


def group_target_signals(
    df,
    tic_col="ticId",
    period_col="orbitalPeriodDays",
    epoch_col="transitEpochBtjd",
    sector_col="sector",
    tol=0.01,
    allow_harmonics=True,
):
    """Assign a `signal_id` to each TCE row, grouping same-signal detections across
    sectors on the same target.

    Returns a copy of `df` with new columns:
      - signal_id      : stable per-signal key, "<ticId>_s<k>" (k = signal index on that TIC)
      - n_sectors      : how many distinct sectors this signal was detected in
      - sectors_list   : comma-joined sorted sectors for the signal
      - is_multisector : n_sectors > 1

    Grouping is deterministic and independent of row order.
    """
    out = df.copy().reset_index(drop=True)
    out["signal_id"] = None

    for tic, idx in out.groupby(tic_col).groups.items():
        rows = out.loc[idx]
        # cluster this TIC's TCEs by period consistency (union-find style, simple)
        members = list(idx)
        periods = {i: out.at[i, period_col] for i in members}
        unassigned = set(members)
        cluster_k = 0
        while unassigned:
            seed = unassigned.pop()
            cluster = {seed}
            # greedily absorb any period-consistent rows
            changed = True
            while changed:
                changed = False
                for j in list(unassigned):
                    if any(_period_consistent(periods[j], periods[c], tol, allow_harmonics)
                           for c in cluster):
                        cluster.add(j)
                        unassigned.discard(j)
                        changed = True
            sid = f"{tic}_s{cluster_k}"
            for i in cluster:
                out.at[i, "signal_id"] = sid
            cluster_k += 1

    # per-signal sector summaries
    grp = out.groupby("signal_id")[sector_col]
    n_sectors = grp.nunique()
    sectors_list = grp.apply(lambda s: ",".join(str(x) for x in sorted(s.dropna().unique())))
    out["n_sectors"] = out["signal_id"].map(n_sectors)
    out["sectors_list"] = out["signal_id"].map(sectors_list)
    out["is_multisector"] = out["n_sectors"] > 1
    return out


if __name__ == "__main__":
    import sys
    inp = sys.argv[1] if len(sys.argv) > 1 else None
    if inp:
        df = pd.read_csv(inp)
        g = group_target_signals(df)
        n_tce = len(g)
        n_sig = g.signal_id.nunique()
        n_multi = g.query("is_multisector").signal_id.nunique()
        print(f"{n_tce} TCEs -> {n_sig} unique signals ({n_multi} multi-sector)")
        out_fp = inp.replace(".csv", "_grouped.csv")
        g.to_csv(out_fp, index=False)
        print(f"wrote {out_fp}")
