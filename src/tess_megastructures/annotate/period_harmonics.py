"""B2: Flag TICs with multiple TCEs at related periods.

For each TIC with more than one TCE, examine all pairs of orbital
periods. Flag pairs whose ratio is close to a small integer or
inverse integer:

- 1:1 (identical periods, possibly different epochs) — duplicate
  detections or SPOC's multi-planet search returning the same signal twice.
- 2:1 or 1:2 — EB detected at half its true period gets aliased.
- 3:1 or 1:3 — higher-order harmonics, less common but seen.

A "match" is when ``|ratio - target| / target < tolerance`` for any
target in {1, 2, 1/2, 3, 1/3}, with ``tolerance`` ~ 1% (configurable).

Output columns added to the TCE table:

- ``period_harmonic_match`` (bool): True if any other TCE on the same
  TIC has a related period.
- ``n_period_matches`` (int): count of related-period TCE peers.
"""

from __future__ import annotations

import pandas as pd


def flag_period_harmonics(
    tces: pd.DataFrame,
    tolerance: float = 0.01,
    targets: tuple[float, ...] = (1.0, 2.0, 0.5, 3.0, 1.0 / 3.0),
) -> pd.DataFrame:
    """Flag TCEs with related-period peers on the same TIC.

    Parameters
    ----------
    tces : DataFrame
        Master TCE table. Must have columns ``ticId`` and ``orbitalPeriodDays``.
    tolerance : float
        Fractional tolerance for ratio matching.
    targets : tuple of float
        Period ratios to consider as "related".

    Returns
    -------
    DataFrame
        Copy of ``tces`` with ``period_harmonic_match`` and
        ``n_period_matches`` columns added.
    """
    raise NotImplementedError
