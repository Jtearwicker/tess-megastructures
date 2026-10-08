"""Build TCE-level CTOI and VSX annotations for review routing."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable

import pandas as pd

ENRICHMENT_COLUMNS = [
    "toi_host_match",
    "toi_signal_match",
    "toi_ids",
    "toi_dispositions",
    "toi_period_ratios",
    "toi_min_period_relative_error",
    "ctoi_host_match",
    "ctoi_signal_match",
    "ctoi_ids",
    "ctoi_dispositions",
    "ctoi_period_ratios",
    "ctoi_min_period_relative_error",
    "vsx_position_match",
    "vsx_signal_match",
    "vsx_names",
    "vsx_types",
    "vsx_period_ratios",
    "vsx_min_period_relative_error",
    "vsx_min_distance_arcsec",
    "catalog_review_flag",
]


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def harmonic_match(
    tce_period: object, catalog_period: object, tolerance: float = 0.01
) -> tuple[bool, str, float | None]:
    """Match periods at 1:2, 1:1, or 2:1 within relative tolerance."""
    tce = _finite_float(tce_period)
    catalog = _finite_float(catalog_period)
    if not tce or not catalog or tce <= 0 or catalog <= 0:
        return False, "", None
    ratio = tce / catalog
    name, expected = min(
        (("1:2", 0.5), ("1:1", 1.0), ("2:1", 2.0)),
        key=lambda item: abs(ratio / item[1] - 1.0),
    )
    relative_error = abs(ratio / expected - 1.0)
    return relative_error <= tolerance, name, relative_error


def _first_present(row: dict, names: tuple[str, ...]) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and not pd.isna(value) and str(value).strip():
            return str(value).strip()
    return ""


def _join_values(values: Iterable[object]) -> str:
    return "|".join(sorted({str(value).strip() for value in values if str(value).strip()}))


def _tic_key(value: object) -> str:
    number = _finite_float(value)
    return str(int(number)) if number is not None else str(value).strip()


def build_catalog_review_enrichment(
    tces: pd.DataFrame,
    ctoi: pd.DataFrame,
    vsx_matches: pd.DataFrame,
    *,
    toi: pd.DataFrame | None = None,
    period_column: str | None = None,
    period_tolerance: float = 0.01,
) -> pd.DataFrame:
    """Annotate TCEs from pinned CTOI and positional VSX match tables.

    ``vsx_matches`` is the result of a positional cross-match and must retain
    the input ``tic_id``. The function performs the signal-level period test;
    a positional/host match alone is recorded separately.
    """
    if "tic_id" not in tces:
        raise KeyError("TCE table requires a 'tic_id' column")
    if period_column is None:
        period_column = next(
            (
                name
                for name in ("orbital_period_days", "tce2_period_days", "period")
                if name in tces
            ),
            None,
        )
    if period_column is None:
        raise KeyError("TCE table requires an orbital-period column")

    ctoi_by_tic: dict[str, list[dict]] = defaultdict(list)
    for item in ctoi.to_dict("records"):
        tic = _first_present(item, ("TIC ID", "tic_id", "TIC", "ticId"))
        if tic:
            ctoi_by_tic[_tic_key(tic)].append(item)

    toi_by_tic: dict[str, list[dict]] = defaultdict(list)
    if toi is not None:
        for item in toi.to_dict("records"):
            tic = _first_present(item, ("TIC ID", "tic_id", "TIC", "ticId"))
            if tic:
                toi_by_tic[_tic_key(tic)].append(item)

    vsx_by_tic: dict[str, list[dict]] = defaultdict(list)
    for item in vsx_matches.to_dict("records"):
        tic = _first_present(item, ("tic_id", "TIC_ID", "TIC", "ticId"))
        if tic:
            vsx_by_tic[_tic_key(tic)].append(item)

    rows: list[dict] = []
    for source in tces.to_dict("records"):
        row = dict(source)
        tic = _tic_key(source["tic_id"])
        tce_period = source.get(period_column)

        toi_rows = toi_by_tic.get(tic, [])
        toi_ephemeris: list[dict] = []
        toi_ratios: list[str] = []
        toi_errors: list[float] = []
        for item in toi_rows:
            matched, ratio, error = harmonic_match(
                tce_period,
                _first_present(item, ("Period (days)", "period", "Period")),
                period_tolerance,
            )
            if matched:
                toi_ephemeris.append(item)
                toi_ratios.append(ratio)
                if error is not None:
                    toi_errors.append(error)

        ctoi_rows = ctoi_by_tic.get(tic, [])
        ctoi_ephemeris: list[dict] = []
        ctoi_ratios: list[str] = []
        ctoi_errors: list[float] = []
        for item in ctoi_rows:
            matched, ratio, error = harmonic_match(
                tce_period,
                _first_present(item, ("Period (days)", "period", "Period")),
                period_tolerance,
            )
            if matched:
                ctoi_ephemeris.append(item)
                ctoi_ratios.append(ratio)
                if error is not None:
                    ctoi_errors.append(error)

        vsx_rows = vsx_by_tic.get(tic, [])
        vsx_ephemeris: list[dict] = []
        vsx_ratios: list[str] = []
        vsx_errors: list[float] = []
        for item in vsx_rows:
            matched, ratio, error = harmonic_match(
                tce_period,
                _first_present(item, ("Period", "period", "Per")),
                period_tolerance,
            )
            if matched:
                vsx_ephemeris.append(item)
                vsx_ratios.append(ratio)
                if error is not None:
                    vsx_errors.append(error)
        distances = [
            distance
            for item in vsx_rows
            if (
                distance := _finite_float(
                    _first_present(item, ("angDist", "_r", "dist", "Distance"))
                )
            )
            is not None
        ]

        row.update(
            {
                "toi_host_match": bool(toi_rows),
                "toi_signal_match": bool(toi_ephemeris),
                "toi_ids": _join_values(
                    _first_present(item, ("TOI", "toi", "toi_id")) for item in toi_rows
                ),
                "toi_dispositions": _join_values(
                    _first_present(item, ("TFOPWG Disposition", "TESS Disposition"))
                    for item in toi_rows
                ),
                "toi_period_ratios": _join_values(toi_ratios),
                "toi_min_period_relative_error": min(toi_errors) if toi_errors else pd.NA,
                "ctoi_host_match": bool(ctoi_rows),
                "ctoi_signal_match": bool(ctoi_ephemeris),
                "ctoi_ids": _join_values(
                    _first_present(item, ("CTOI", "ctoi")) for item in ctoi_rows
                ),
                "ctoi_dispositions": _join_values(
                    _first_present(item, ("TFOPWG Disposition", "User Disposition"))
                    for item in ctoi_rows
                ),
                "ctoi_period_ratios": _join_values(ctoi_ratios),
                "ctoi_min_period_relative_error": min(ctoi_errors) if ctoi_errors else pd.NA,
                "vsx_position_match": bool(vsx_rows),
                "vsx_signal_match": bool(vsx_ephemeris),
                "vsx_names": _join_values(
                    _first_present(item, ("Name", "name")) for item in vsx_rows
                ),
                "vsx_types": _join_values(
                    _first_present(item, ("Type", "type")) for item in vsx_rows
                ),
                "vsx_period_ratios": _join_values(vsx_ratios),
                "vsx_min_period_relative_error": min(vsx_errors) if vsx_errors else pd.NA,
                "vsx_min_distance_arcsec": min(distances) if distances else pd.NA,
                "catalog_review_flag": bool(toi_rows or ctoi_rows or vsx_rows),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)
