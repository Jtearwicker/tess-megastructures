"""Period-matched eclipsing-binary training labels.

Separate from ``annotate/catalog_xmatch.py``, which flags EB *TIC membership*
to gate the survivor set. That coarse flag is right for gating, but too loose
for training labels: a TIC that hosts a catalogued EB can also carry a real
planet TCE or a second signal at an unrelated period, and labeling that TCE as
an EB would feed the classifier a dirty positive.

This module labels a TCE as an EB positive only when its TIC is a vetted EB and
its orbital period matches the catalogued period within tolerance at a 1:1, 2:1,
or 1:2 ratio (the factor-of-two ratios matter because SPOC frequently detects an
EB at half its true period). The label is the classifier's clean positive; the
pipeline's ``flag_prsa_eb`` is untouched.

Columns added by :func:`add_period_matched_eb_labels`:

- ``label_prsa_eb`` (bool): period-matched EB positive.
- ``label_prsa_period_days`` (Float64): the catalogued period that matched,
  NaN when unmatched (for inspection).
- ``label_prsa_ratio`` (Float64): which ratio matched (1.0, 2.0, or 0.5),
  NaN when unmatched. Lets you see how many EBs were caught at half period.

Rows are never dropped. A missing catalog degrades to an all-False label.
"""

from __future__ import annotations

import logging

import pandas as pd

from tess_megastructures.annotate.period_harmonics import EB_LABEL_TARGETS, matched_ratio

logger = logging.getLogger(__name__)


def _catalog_periods_by_tic(
    prsa: pd.DataFrame, catalog_period_col: str
) -> dict[int, list[float]]:
    """Map TIC -> list of catalogued periods (a few TICs carry >1 EB entry)."""
    out: dict[int, list[float]] = {}
    for tic, per in zip(prsa["ticId"].astype("int64"), prsa[catalog_period_col]):
        try:
            p = float(per)
        except (TypeError, ValueError):
            continue
        if p > 0.0:
            out.setdefault(int(tic), []).append(p)
    return out


def add_period_matched_eb_labels(
    df: pd.DataFrame,
    prsa: pd.DataFrame | None = None,
    tolerance: float = 0.01,
    targets: tuple[float, ...] = EB_LABEL_TARGETS,
    catalog_period_col: str = "Per",
    period_col: str = "orbital_period_days",
) -> pd.DataFrame:
    """Add the period-matched Prsa EB training label to a TCE table.

    Parameters
    ----------
    df : DataFrame
        TCE table; must have ``tic_id`` (int) and ``period_col``.
    prsa : DataFrame or None
        Prsa+2022 catalog with a ``ticId`` column (from ``prsa2022.load`` or an
        equivalent) and a period column named ``catalog_period_col``. None or
        empty yields an all-False label with a warning.
    tolerance : float
        Fractional tolerance for the period match.
    targets : tuple of float
        Allowed ratios (default 1:1, 2:1, 1:2).
    catalog_period_col : str
        Period column in ``prsa`` (VizieR J/ApJS/258/16 calls it ``Per``, days).
    period_col : str
        TCE period column (default matches the DV parser output).

    Returns
    -------
    DataFrame
        Copy of ``df`` with ``label_prsa_eb``, ``label_prsa_period_days``, and
        ``label_prsa_ratio`` added. Rows are never dropped.
    """
    out = df.copy()
    if "tic_id" not in out.columns:
        raise KeyError("period-matched EB labels require a 'tic_id' column")
    if period_col not in out.columns:
        raise KeyError(f"period-matched EB labels require a {period_col!r} column")

    out["label_prsa_eb"] = False
    out["label_prsa_period_days"] = pd.array([pd.NA] * len(out), dtype="Float64")
    out["label_prsa_ratio"] = pd.array([pd.NA] * len(out), dtype="Float64")

    if prsa is None or prsa.empty:
        logger.warning("Prsa+2022 catalog empty/missing; label_prsa_eb all False")
        return out
    if "ticId" not in prsa.columns:
        raise KeyError("Prsa catalog must have a 'ticId' column (run prsa2022.load first)")
    if catalog_period_col not in prsa.columns:
        raise KeyError(
            f"Prsa catalog must have a {catalog_period_col!r} period column; "
            f"got {list(prsa.columns)}"
        )

    cat_periods = _catalog_periods_by_tic(prsa, catalog_period_col)

    # Nullable int so a null TIC (should not occur from the parser) degrades to
    # an unlabeled row rather than raising on the conversion.
    tic_series = pd.to_numeric(out["tic_id"], errors="coerce").astype("Int64")

    labels: list[bool] = []
    matched_period: list[float | None] = []
    matched_r: list[float | None] = []
    for tic, p_tce in zip(tic_series, out[period_col]):
        hit_period = None
        hit_ratio = None
        if not pd.isna(tic):
            for p_cat in cat_periods.get(int(tic), ()):
                r = matched_ratio(p_tce, p_cat, tolerance, targets)
                if r is not None:
                    hit_period, hit_ratio = p_cat, r
                    break
        labels.append(hit_period is not None)
        matched_period.append(hit_period)
        matched_r.append(hit_ratio)

    out["label_prsa_eb"] = labels
    out["label_prsa_period_days"] = pd.array(
        [p if p is not None else pd.NA for p in matched_period], dtype="Float64"
    )
    out["label_prsa_ratio"] = pd.array(
        [r if r is not None else pd.NA for r in matched_r], dtype="Float64"
    )

    on_eb_tic = tic_series.isin(list(cat_periods.keys()))
    logger.info(
        "Period-matched Prsa EB labels: %d of %d TCEs labeled; "
        "%d TCEs sit on a Prsa TIC, so %d were on an EB TIC but not period-matched",
        int(pd.Series(labels).sum()),
        len(out),
        int(on_eb_tic.sum()),
        int(on_eb_tic.sum()) - int(pd.Series(labels).sum()),
    )
    return out
