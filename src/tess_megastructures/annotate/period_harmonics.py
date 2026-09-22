"""B2: Period-harmonic matching.

One ratio test, two uses:

- ``periods_match`` / ``matched_ratio``: does one period match another within a
  fractional tolerance at any of a set of integer / inverse-integer ratios?
  The core helper, reused by the catalog EB-label cross-match
  (``annotate/eb_labels.py``).
- ``flag_period_harmonics``: for each TIC with more than one TCE, flag TCEs
  whose orbital period is a small-integer ratio of another TCE on the same TIC
  (1:1 duplicate detections, 2:1 / 1:2 aliasing, 3:1 / 1:3 higher harmonics).

A "match" is ``|p1/p2 / target - 1| < tolerance`` for any target ratio.

Output columns added to the TCE table by ``flag_period_harmonics``:

- ``period_harmonic_match`` (bool): another TCE on the same TIC has a related period.
- ``n_period_matches`` (int): count of related-period peers.
"""

from __future__ import annotations

import pandas as pd

# Ratios for the TIC-internal peer flag (includes third harmonics).
HARMONIC_TARGETS: tuple[float, ...] = (1.0, 2.0, 0.5, 3.0, 1.0 / 3.0)
# Ratios for EB catalog-period label matching: 1:1, 2:1, 1:2 only. SPOC often
# detects an EB at half its true period (the secondary reads as a transit), so
# the factor-of-two ratios are the common case, not an edge case.
EB_LABEL_TARGETS: tuple[float, ...] = (1.0, 2.0, 0.5)


def matched_ratio(
    p1: float | None,
    p2: float | None,
    tolerance: float = 0.01,
    targets: tuple[float, ...] = EB_LABEL_TARGETS,
) -> float | None:
    """Return the first target ratio that ``p1 / p2`` matches within a fractional
    ``tolerance``, or None if none match.

    Both periods must be positive and finite. Returns None on missing or
    non-positive input rather than raising, so it is safe to map over a column.
    """
    try:
        a, b = float(p1), float(p2)
    except (TypeError, ValueError):
        return None
    if not (a > 0.0 and b > 0.0):
        return None
    ratio = a / b
    for t in targets:
        if abs(ratio / t - 1.0) < tolerance:
            return t
    return None


def periods_match(
    p1: float | None,
    p2: float | None,
    tolerance: float = 0.01,
    targets: tuple[float, ...] = EB_LABEL_TARGETS,
) -> bool:
    """True if ``p1 / p2`` matches any ratio in ``targets`` within ``tolerance``."""
    return matched_ratio(p1, p2, tolerance, targets) is not None


def flag_period_harmonics(
    tces: pd.DataFrame,
    tolerance: float = 0.01,
    targets: tuple[float, ...] = HARMONIC_TARGETS,
    tic_col: str = "tic_id",
    period_col: str = "orbital_period_days",
) -> pd.DataFrame:
    """Flag TCEs with related-period peers on the same TIC.

    For each TIC with more than one TCE, every pair of orbital periods is tested
    with :func:`periods_match`. A TCE is flagged if any *other* TCE on the same
    TIC has a related period.

    Parameters
    ----------
    tces : DataFrame
        Master TCE table. Must have ``tic_col`` and ``period_col``.
    tolerance : float
        Fractional tolerance for ratio matching.
    targets : tuple of float
        Period ratios treated as "related".
    tic_col, period_col : str
        Column names (defaults match the DV parser output).

    Returns
    -------
    DataFrame
        Copy of ``tces`` with ``period_harmonic_match`` (bool) and
        ``n_period_matches`` (int) added. Rows are never dropped.
    """
    out = tces.copy()
    for col in (tic_col, period_col):
        if col not in out.columns:
            raise KeyError(f"flag_period_harmonics requires a {col!r} column")

    match = pd.Series(False, index=out.index)
    counts = pd.Series(0, index=out.index, dtype="int64")

    for idx in out.groupby(tic_col).groups.values():
        if len(idx) < 2:
            continue
        periods = out.loc[idx, period_col]
        for i in idx:
            n = 0
            for j in idx:
                if j != i and periods_match(periods.loc[i], periods.loc[j], tolerance, targets):
                    n += 1
            counts.loc[i] = n
            match.loc[i] = n > 0

    out["period_harmonic_match"] = match
    out["n_period_matches"] = counts
    return out
