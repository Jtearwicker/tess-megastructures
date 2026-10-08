"""Non-destructive review routing from CTOI and VSX annotations.

This module is deliberately separate from :mod:`catalog_xmatch`: its outputs
prioritize human review but never participate in candidate-selection flags.
Planet evidence has precedence over variable-star evidence so a catalog match
cannot silently reject a confirmed planet or community planet candidate.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CATALOG_ROUTE_SCHEMA_VERSION = "1.0.0"
CATALOG_ROUTE_COLUMNS = [
    "catalog_route_schema_version",
    "catalog_review_route",
    "catalog_route_reason",
    "catalog_automatic_veto",
]

_ENRICHMENT_COLUMNS = [
    "label",
    "ctoi_host_match",
    "ctoi_signal_match",
    "ctoi_dispositions",
    "vsx_position_match",
    "vsx_signal_match",
    "vsx_types",
]
_EB_TYPES = {"EA", "EB", "EW", "ELL", "EA/WD", "E", "EP"}


def load_catalog_review_enrichment(path: Path) -> pd.DataFrame:
    """Load a precomputed CTOI/VSX enrichment table from CSV or Parquet."""
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"Unsupported catalog review enrichment format: {path}")


def _truth(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _values(value: object) -> set[str]:
    if pd.isna(value):
        return set()
    return {item.strip().upper() for item in str(value).split("|") if item.strip()}


def _route(row: pd.Series) -> tuple[str, str]:
    dispositions = _values(row.get("ctoi_dispositions"))
    vsx_types = _values(row.get("vsx_types"))
    if str(row.get("label", "")).strip().lower() == "planet":
        return "protect_confirmed_planet", "existing confirmed-planet control"
    if _truth(row.get("ctoi_signal_match")) and dispositions & {"CP", "PC", "APC"}:
        return "protect_planet_candidate", "CTOI ephemeris match with CP/PC/APC disposition"
    if _truth(row.get("ctoi_signal_match")) and "FP" in dispositions:
        return "review_known_toi_fp", "CTOI ephemeris match with FP disposition"
    if _truth(row.get("vsx_signal_match")) and vsx_types & _EB_TYPES:
        return "review_catalog_eb", "VSX ephemeris match with EB-like variable type"
    if _truth(row.get("vsx_signal_match")):
        return "review_period_matched_variable", "VSX ephemeris match with non-EB variable type"
    if _truth(row.get("ctoi_host_match")) or _truth(row.get("vsx_position_match")):
        return "review_catalog_context", "catalog host/position match without TCE-period match"
    return "standard_review", "no CTOI or VSX match"


def add_catalog_review_routes(
    df: pd.DataFrame,
    enrichment: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Attach CTOI/VSX review routes without changing selection eligibility.

    The enrichment is joined using the most specific common TCE key: always
    ``tic_id``, then ``planet_number`` and ``sector`` when both tables contain
    them. Duplicate enrichment rows for that key are rejected rather than
    multiplying TCE rows. With no enrichment, every TCE gets
    ``standard_review``.
    """
    if "tic_id" not in df.columns:
        raise KeyError("catalog review routing requires a 'tic_id' column")

    out = df.copy()
    if enrichment is not None and not enrichment.empty:
        if "tic_id" not in enrichment.columns:
            raise KeyError("catalog review enrichment requires a 'tic_id' column")
        keys = ["tic_id"] + [
            key for key in ("planet_number", "sector") if key in out.columns and key in enrichment
        ]
        if enrichment.duplicated(keys).any():
            raise ValueError(f"catalog review enrichment has duplicate rows for key {keys}")
        columns = keys + [column for column in _ENRICHMENT_COLUMNS if column in enrichment]
        overlap = [
            column
            for column in _ENRICHMENT_COLUMNS
            if column in out.columns and column in enrichment.columns
        ]
        out = out.drop(columns=overlap).merge(
            enrichment[columns], how="left", on=keys, validate="many_to_one"
        )

    routes = out.apply(_route, axis=1, result_type="expand")
    out["catalog_route_schema_version"] = CATALOG_ROUTE_SCHEMA_VERSION
    out["catalog_review_route"] = routes[0]
    out["catalog_route_reason"] = routes[1]
    # Contract invariant: review annotations never veto a TCE automatically.
    out["catalog_automatic_veto"] = False
    return out
