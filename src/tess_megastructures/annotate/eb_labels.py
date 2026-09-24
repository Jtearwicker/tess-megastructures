"""Period-matched training labels for the EB classifier.

Separate from ``annotate/catalog_xmatch.py``, which flags EB *TIC membership*
to gate the survivor set. That coarse flag is right for gating, but too loose
for training labels: a TIC that hosts a catalogued EB can also carry a real
planet TCE or a second signal at an unrelated period, and labeling that TCE as
an EB would feed the classifier a dirty positive.

Two layers:

1. :func:`add_period_matched_eb_labels`: the Prsa EB positive on its own.
   Columns ``label_prsa_eb`` (bool), ``label_prsa_period_days`` and
   ``label_prsa_ratio`` (Float64). Unchanged, so ``build_eb_labels.py`` works.
2. :func:`add_training_labels`: the full label set. Every TCE gets exactly one
   of ``eb``, ``planet``, ``fp``, ``quarantine``, ``unlabeled`` in ``label``,
   the rule that fired in ``label_reason``, and provenance columns so any call
   can be revisited without a rerun.

Matching (fractional period tolerance, default 1%):

- EB (Prsa, plus any ``extra_eb`` catalogs): 1:1, 2:1, 1:2. SPOC often detects
  an EB at half its true period.
- Planet (confirmed planets from ``pscomppars``, TOI CP and KP): 1:1 and 2:1
  (2:1 when alternate transits fall in gaps). A TCE at half a planet's period
  has no planet signal to detect there, so it is quarantined, not labeled planet.
- TOI FP: 1:1, 2:1, 1:2 (false positives are often EBs).

Precedence, first hit wins:

1. EB match and planet match           -> quarantine  (eb_planet_conflict)
2. EB match                            -> eb          (prsa_eb / extra_eb)
3. On an EB host, not EB-matched       -> quarantine  (eb_host_unmatched)
4. Planet match at 1:1 or 2:1          -> planet      (planet_<source>)
5. TCE at half a planet's period       -> quarantine  (planet_half_period)
6. TOI FP match                        -> fp          (toi_fp)
7. Otherwise                           -> unlabeled   (none)

Quarantine is a training label only: nothing is dropped from any table.
Rows are never dropped. A missing catalog degrades to empty with a warning.
"""

from __future__ import annotations

import logging
import numbers
import re

import pandas as pd

from tess_megastructures.annotate.period_harmonics import EB_LABEL_TARGETS, matched_ratio

logger = logging.getLogger(__name__)

LABELS: tuple[str, ...] = ("eb", "planet", "fp", "quarantine", "unlabeled")
# Planet matches allow 1:1 and 2:1 only; a 1:2 hit is scored separately.
PLANET_TARGETS: tuple[float, ...] = (1.0, 2.0)
# When several catalog entries on one TIC match, 1:1 beats 2:1 beats 1:2.
_RATIO_PRIORITY: tuple[float, ...] = (1.0, 2.0, 0.5)


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


# ---------------------------------------------------------------------------
# Full training-label set
# ---------------------------------------------------------------------------


def _tic_int(value) -> int | None:
    """TIC as an int from an int, a float, or a string such as 'TIC 12345'."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        f = float(value)
        return int(f) if f.is_integer() else None
    m = re.search(r"\d+", str(value))
    return int(m.group()) if m else None


def _index_catalog(
    df: pd.DataFrame | None,
    tic_col: str,
    period_col: str,
    meta_cols: tuple[str, ...] = (),
    **const,
) -> dict[int, list[tuple[float, dict]]]:
    """Map TIC -> [(period, meta)], skipping rows without a TIC or positive period."""
    out: dict[int, list[tuple[float, dict]]] = {}
    if df is None or len(df) == 0:
        return out
    for col in (tic_col, period_col):
        if col not in df.columns:
            raise KeyError(f"catalog is missing column {col!r}; got {list(df.columns)[:20]}")
    cols = [tic_col, period_col] + [c for c in meta_cols if c in df.columns]
    for rec in df[cols].to_dict("records"):
        tic = _tic_int(rec[tic_col])
        try:
            p = float(rec[period_col])
        except (TypeError, ValueError):
            continue
        if tic is None or not p > 0.0:  # also rejects NaN
            continue
        meta = {**const, **{c: rec[c] for c in cols[2:]}}
        out.setdefault(tic, []).append((p, meta))
    return out


def _merge(*maps: dict[int, list]) -> dict[int, list]:
    out: dict[int, list] = {}
    for m in maps:
        for tic, entries in m.items():
            out.setdefault(tic, []).extend(entries)
    return out


def _best_match(p_tce, entries, tolerance: float, targets=_RATIO_PRIORITY):
    """Best catalog match for one TCE: 1:1 beats 2:1 beats 1:2, ties keep catalog
    order. Returns (ratio, catalog_period, meta) or None."""
    best = None
    for p_cat, meta in entries:
        r = matched_ratio(p_tce, p_cat, tolerance, targets)
        if r is None:
            continue
        rank = _RATIO_PRIORITY.index(r)
        if best is None or rank < best[0]:
            best = (rank, r, p_cat, meta)
    return None if best is None else best[1:]


def _clean_disp(s: pd.Series) -> pd.Series:
    return s.astype("object").where(s.notna(), "").astype(str).str.strip().str.upper()


def add_training_labels(
    df: pd.DataFrame,
    prsa: pd.DataFrame | None = None,
    planets: pd.DataFrame | None = None,
    toi: pd.DataFrame | None = None,
    extra_eb: list[tuple[pd.DataFrame, str]] | None = None,
    tolerance: float = 0.01,
    catalog_period_col: str = "Per",
    period_col: str = "orbital_period_days",
) -> pd.DataFrame:
    """Assign every TCE one training label (see module docstring for the rules).

    Parameters
    ----------
    df : DataFrame
        TCE table with ``tic_id`` and ``period_col``.
    prsa : DataFrame or None
        Prsa+2022 with ``ticId`` and ``catalog_period_col``.
    planets : DataFrame or None
        Confirmed planets (Exoplanet Archive ``pscomppars``): ``tic_id``
        (e.g. 'TIC 12345'), ``pl_orbper``, optional ``pl_name``.
    toi : DataFrame or None
        TOI table: ``tid``, ``pl_orbper``, ``tfopwg_disp``, optional ``toi``.
    extra_eb : list of (DataFrame, period column) or None
        Additional vetted EB catalogs, each with ``ticId``. Their TICs join the
        EB-host set and their periods count as EB matches. Empty for run 1.

    Returns
    -------
    DataFrame
        Copy of ``df`` with the Prsa label columns plus ``on_eb_host``,
        ``planet_match``, ``planet_half_match``, ``planet_match_source``,
        ``planet_match_name``, ``planet_match_period_days``,
        ``planet_match_ratio``, ``toi_match``, ``toi_disp``,
        ``toi_match_ratio``, ``toi_fp_match``, ``label``, ``label_reason``.
    """
    out = add_period_matched_eb_labels(
        df, prsa, tolerance=tolerance,
        catalog_period_col=catalog_period_col, period_col=period_col,
    )

    # EB hosts: every TIC in a vetted EB catalog, whether or not it has a period.
    eb_hosts: set[int] = set()
    if prsa is not None and len(prsa):
        eb_hosts |= {t for t in (_tic_int(v) for v in prsa["ticId"]) if t is not None}
    extra_map: dict[int, list] = {}
    for cat, pcol in extra_eb or []:
        extra_map = _merge(extra_map, _index_catalog(cat, "ticId", pcol))
        eb_hosts |= {t for t in (_tic_int(v) for v in cat["ticId"]) if t is not None}

    if planets is None or len(planets) == 0:
        logger.warning("confirmed-planet catalog empty/missing; no pscomppars planet labels")
    planet_map = _index_catalog(planets, "tic_id", "pl_orbper", ("pl_name",), source="pscomppars")

    fp_map: dict[int, list] = {}
    toi_map: dict[int, list] = {}
    if toi is None or len(toi) == 0:
        logger.warning("TOI table empty/missing; no TOI planet or FP labels")
    else:
        disp = _clean_disp(toi["tfopwg_disp"])
        cp = _index_catalog(toi[disp == "CP"], "tid", "pl_orbper", ("toi",), source="toi_cp")
        kp = _index_catalog(toi[disp == "KP"], "tid", "pl_orbper", ("toi",), source="toi_kp")
        planet_map = _merge(planet_map, cp, kp)  # pscomppars first, so it wins ties
        fp_map = _index_catalog(toi[disp == "FP"], "tid", "pl_orbper", ("toi",))
        toi_map = _index_catalog(toi.assign(_disp=disp), "tid", "pl_orbper", ("toi", "_disp"))

    tics = pd.to_numeric(out["tic_id"], errors="coerce").astype("Int64")
    cols: dict[str, list] = {k: [] for k in (
        "on_eb_host", "planet_match", "planet_half_match", "planet_match_source",
        "planet_match_name", "planet_match_period_days", "planet_match_ratio",
        "toi_match", "toi_disp", "toi_match_ratio", "toi_fp_match", "label", "label_reason",
    )}

    for tic, p, eb_prsa in zip(tics, out[period_col], out["label_prsa_eb"]):
        t = None if pd.isna(tic) else int(tic)
        ext = _best_match(p, extra_map.get(t, ()), tolerance, EB_LABEL_TARGETS) if t is not None else None
        is_eb = bool(eb_prsa) or ext is not None
        host = t in eb_hosts if t is not None else False
        pl = _best_match(p, planet_map.get(t, ()), tolerance) if t is not None else None
        planet_full = pl is not None and pl[0] in PLANET_TARGETS
        planet_half = pl is not None and pl[0] == 0.5
        fp = _best_match(p, fp_map.get(t, ()), tolerance) if t is not None else None
        tm = _best_match(p, toi_map.get(t, ()), tolerance) if t is not None else None

        if is_eb and planet_full:
            label, reason = "quarantine", "eb_planet_conflict"
        elif is_eb:
            label, reason = "eb", ("prsa_eb" if eb_prsa else "extra_eb")
        elif host:
            label, reason = "quarantine", "eb_host_unmatched"
        elif planet_full:
            label, reason = "planet", f"planet_{pl[2]['source']}"
        elif planet_half:
            label, reason = "quarantine", "planet_half_period"
        elif fp is not None:
            label, reason = "fp", "toi_fp"
        else:
            label, reason = "unlabeled", "none"

        name = None
        if pl is not None:
            meta = pl[2]
            if meta["source"] == "pscomppars":
                name = meta.get("pl_name")
            elif meta.get("toi") is not None and pd.notna(meta.get("toi")):
                name = f"TOI-{meta['toi']}"
        cols["on_eb_host"].append(host)
        cols["planet_match"].append(planet_full)
        cols["planet_half_match"].append(planet_half)
        cols["planet_match_source"].append(pl[2]["source"] if pl else None)
        cols["planet_match_name"].append(name)
        cols["planet_match_period_days"].append(pl[1] if pl else None)
        cols["planet_match_ratio"].append(pl[0] if pl else None)
        cols["toi_match"].append(tm[2].get("toi") if tm else None)
        cols["toi_disp"].append((tm[2].get("_disp") or None) if tm else None)
        cols["toi_match_ratio"].append(tm[0] if tm else None)
        cols["toi_fp_match"].append(fp is not None)
        cols["label"].append(label)
        cols["label_reason"].append(reason)

    for k in ("on_eb_host", "planet_match", "planet_half_match", "toi_fp_match"):
        out[k] = pd.array(cols[k], dtype="boolean")
    for k in ("planet_match_source", "planet_match_name", "toi_disp", "label", "label_reason"):
        out[k] = pd.array(cols[k], dtype="string")
    for k in ("planet_match_period_days", "planet_match_ratio", "toi_match", "toi_match_ratio"):
        out[k] = pd.array([pd.NA if v is None else float(v) for v in cols[k]], dtype="Float64")

    logger.info("Training labels: %s", out["label"].value_counts().to_dict())
    return out


def summarize_training_labels(out: pd.DataFrame) -> dict:
    """Label sizes and the edge-case counts that decide the labeling rules."""
    lab, reason = out["label"], out["label_reason"]
    planet = out["planet_match"].fillna(False).astype(bool)
    half = out["planet_half_match"].fillna(False).astype(bool)
    fpm = out["toi_fp_match"].fillna(False).astype(bool)
    host_q = (reason == "eb_host_unmatched").fillna(False).astype(bool)
    return {
        "n_tces": len(out),
        "n_tics": int(out["tic_id"].nunique()),
        "labels": {k: int((lab == k).sum()) for k in LABELS},
        "reasons": {k: int(v) for k, v in reason.value_counts().items()},
        "edge_cases": {
            "eb_and_planet_conflict": int((reason == "eb_planet_conflict").sum()),
            "planet_match_on_eb_host": int((planet & host_q).sum()),
            "planet_half_period_quarantined": int((reason == "planet_half_period").sum()),
            "planet_half_on_eb_host": int((half & host_q).sum()),
            "toi_fp_also_catalog_eb": int((fpm & (lab == "eb")).sum()),
            "toi_fp_on_eb_host_unmatched": int((fpm & host_q).sum()),
        },
        "planet_sources": {
            k: int(v) for k, v in out.loc[lab == "planet", "planet_match_source"].value_counts().items()
        },
        "unlabeled_toi_disp": {
            k: int(v) for k, v in out.loc[lab == "unlabeled", "toi_disp"].value_counts().items()
        },
    }
