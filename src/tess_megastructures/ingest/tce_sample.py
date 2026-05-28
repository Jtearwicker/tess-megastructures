"""Subsystem A (Definition B): build the v1 TCE sample.

Produces ``tce_sample_v1.parquet``: every SPOC FFI Threshold Crossing
Event, aggregated across sectors, with stellar parameters attached and
boolean selection-cut columns.

IMPORTANT -- Definition B vs Definition A
-----------------------------------------
This module builds the TCE POPULATION (Definition B): the set of TCEs the
v1 MegaMiner pipeline operates on. It is NOT the stellar occurrence-rate
denominator (Definition A, the "parent sample"), which would count all
SEARCHED stars including those that produced no TCE. Definition A is
deferred to v2; see ``parent_sample.py`` (the v2 placeholder) and
``docs/decisions.md``.

Row granularity
---------------
One row per (tic_id, planet_number, sector). The same physical signal
observed in multiple sectors yields multiple rows; downstream stages may
collapse as needed. A ``run_type`` column distinguishes single-sector from
multi-sector detections.

Stellar parameters
------------------
DV-extracted stellar params (effective_temp, radius, log_g, tess_mag, ...)
are the PRIMARY source -- they are present for every TCE straight from the
parser, with no cross-match coverage gaps. Doyle+24 Gaia-derived params
(``doyle_parallax``, ``doyle_ruwe``, ...) are an ENRICHMENT layer,
attached where the TIC cross-match hits and flagged by
``has_doyle_params``.

Contract with the Doyle loader
------------------------------
``enrich_with_doyle`` expects the Doyle DataFrame to ALREADY have
``doyle_``-prefixed columns (which is what ``catalogs.doyle2024.load_doyle2024``
produces). The enrichment merges those columns in directly; it does NOT
re-prefix. Callers passing in unprefixed Doyle data will end up with
column names ``apply_cuts`` does not recognize.

Selection cuts
--------------
Each cut from ``configs/tce_sample_v1.yaml`` produces a boolean column.
Rows are NEVER dropped. ``in_clean_sample`` is the AND of the cuts listed
under ``required_for_clean`` in the config.
"""

from __future__ import annotations

import datetime as dt
import glob
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Aggregation
# -------------------------------------------------------------------------


def aggregate_parsed_sectors(parsed_paths: list[Path]) -> pd.DataFrame:
    """Concatenate per-sector parsed Parquet files into one TCE table.

    Parameters
    ----------
    parsed_paths : list of Path
        Paths to per-sector Parquet files produced by the parser.

    Returns
    -------
    pandas.DataFrame
        Concatenated TCEs. Empty DataFrame if no inputs.
    """
    if not parsed_paths:
        logger.warning("No parsed Parquet files provided to aggregate.")
        return pd.DataFrame()

    frames = []
    for path in parsed_paths:
        try:
            frames.append(pd.read_parquet(path))
        except Exception as e:  # noqa: BLE001
            logger.warning("Skipping unreadable Parquet %s: %s", path, e)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def find_parsed_sectors(parsed_dir: Path) -> list[Path]:
    """Find per-sector parsed Parquet files in a directory."""
    pattern = str(parsed_dir / "tce_dv_metrics_*.parquet")
    return sorted(Path(p) for p in glob.glob(pattern))


# -------------------------------------------------------------------------
# Run-type classification
# -------------------------------------------------------------------------


def classify_run_type(df: pd.DataFrame) -> pd.DataFrame:
    """Add a ``run_type`` column: 'single_sector' or 'multi_sector'.

    Multi-sector detections are identified by the parser's
    ``n_difference_images`` column: a value > 1 indicates the DV report
    combined multiple sectors. Falls back to 'single_sector' when the
    column is absent.
    """
    out = df.copy()
    if "n_difference_images" in out.columns:
        out["run_type"] = out["n_difference_images"].apply(
            lambda n: "multi_sector" if (pd.notna(n) and n > 1) else "single_sector"
        )
    else:
        out["run_type"] = "single_sector"
    return out


# -------------------------------------------------------------------------
# Doyle+24 enrichment
# -------------------------------------------------------------------------


def enrich_with_doyle(
    df: pd.DataFrame,
    doyle: pd.DataFrame | None,
) -> pd.DataFrame:
    """Left-join Doyle+24 Gaia-derived params onto the TCE table by TIC.

    Adds ``has_doyle_params`` (True where the cross-match hit).

    The Doyle DataFrame is expected to come from
    ``catalogs.doyle2024.load_doyle2024`` and ALREADY have ``doyle_``-prefixed
    columns -- this function merges those columns straight in. It does
    NOT re-prefix; doing so would produce ``doyle_doyle_*`` names that
    ``apply_cuts`` could not find.

    Parameters
    ----------
    df : DataFrame
        Aggregated TCE table (must have ``tic_id``).
    doyle : DataFrame or None
        Doyle+24 table with a ``tic_id`` column plus already-prefixed
        ``doyle_*`` columns. If None, all rows get ``has_doyle_params =
        False`` and no Doyle columns are attached.
    """
    out = df.copy()

    if doyle is None or doyle.empty:
        out["has_doyle_params"] = False
        return out

    doyle_indexed = doyle.drop_duplicates(subset="tic_id").set_index("tic_id")

    out = out.merge(
        doyle_indexed,
        how="left",
        left_on="tic_id",
        right_index=True,
    )
    # has_doyle_params: did this TIC appear in Doyle+24?
    matched_tics = set(doyle_indexed.index)
    out["has_doyle_params"] = out["tic_id"].isin(matched_tics)
    return out


# -------------------------------------------------------------------------
# Selection cuts
# -------------------------------------------------------------------------


def apply_cuts(df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Apply selection cuts as boolean columns; never drop rows.

    Produces one boolean column per cut, plus ``has_valid_stellar_params``
    and the final ``in_clean_sample`` flag (AND of the cuts listed under
    ``required_for_clean`` in the config).
    """
    out = df.copy()
    cuts = config.get("stellar_cuts", {})

    # Brightness cut (DV-extracted tess_mag).
    tmag_min = cuts.get("tmag_min")
    tmag_max = cuts.get("tmag_max")
    if "tess_mag" in out.columns and tmag_min is not None and tmag_max is not None:
        out["passed_tmag_cut"] = out["tess_mag"].between(tmag_min, tmag_max)
    else:
        out["passed_tmag_cut"] = pd.NA

    # Surface gravity cut (DV-extracted log_g).
    log_g_min = cuts.get("log_g_min")
    if "log_g" in out.columns and log_g_min is not None:
        out["passed_log_g_cut"] = out["log_g"] >= log_g_min
    else:
        out["passed_log_g_cut"] = pd.NA

    # Parallax SNR cut (Doyle+24 enrichment; only where present).
    plx_min = cuts.get("parallax_over_error_min")
    if "doyle_parallax_over_error" in out.columns and plx_min is not None:
        out["passed_parallax_cut"] = out["doyle_parallax_over_error"] >= plx_min
    else:
        out["passed_parallax_cut"] = pd.NA

    # RUWE cut (Doyle+24 enrichment; only where present).
    ruwe_max = cuts.get("ruwe_max_for_clean")
    if "doyle_ruwe" in out.columns and ruwe_max is not None:
        out["passed_ruwe_cut"] = out["doyle_ruwe"] < ruwe_max
    else:
        out["passed_ruwe_cut"] = pd.NA

    # Valid stellar params: all required-valid columns non-null.
    require_valid = config.get("require_valid", [])
    present = [c for c in require_valid if c in out.columns]
    if present:
        out["has_valid_stellar_params"] = out[present].notna().all(axis=1)
    else:
        out["has_valid_stellar_params"] = pd.NA

    # in_clean_sample: AND of the required-for-clean boolean columns.
    required = config.get("required_for_clean", [])
    present_required = [c for c in required if c in out.columns]
    if present_required:
        # Treat NA as False for the AND (a missing cut result fails clean).
        clean = out[present_required].fillna(False).astype(bool).all(axis=1)
        out["in_clean_sample"] = clean
    else:
        out["in_clean_sample"] = False

    return out


# -------------------------------------------------------------------------
# Top-level driver
# -------------------------------------------------------------------------


def build_tce_sample(
    parsed_paths: list[Path],
    config: dict[str, Any],
    output_path: Path | None = None,
    doyle: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the v1 TCE sample from parsed sector Parquets.

    Steps: aggregate -> classify run type -> enrich with Doyle+24 ->
    apply cuts -> add provenance -> (optionally) write Parquet.

    Parameters
    ----------
    parsed_paths : list of Path
        Per-sector parsed Parquet files (parser outputs).
    config : dict
        Parsed ``tce_sample_v1.yaml``.
    output_path : Path, optional
        If given, write the result to this Parquet path.
    doyle : DataFrame, optional
        Doyle+24 table for enrichment, already produced by
        ``catalogs.doyle2024.load_doyle2024`` (i.e. with ``doyle_``-prefixed
        columns). If None, no enrichment is applied.

    Returns
    -------
    DataFrame
        The TCE sample. Empty if no input rows.
    """
    df = aggregate_parsed_sectors(parsed_paths)
    if df.empty:
        logger.warning("Aggregation produced no rows; TCE sample is empty.")
        return df

    df = classify_run_type(df)
    df = enrich_with_doyle(df, doyle)
    df = apply_cuts(df, config)

    # Provenance.
    from tess_megastructures import __version__ as pkg_version

    df["tce_sample_version"] = config.get("version", "unknown")
    df["built_with_package_version"] = pkg_version
    df["built_at"] = dt.datetime.now(dt.UTC).isoformat()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, index=False)
        logger.info(
            "Wrote TCE sample: %d rows, %d in clean sample -> %s",
            len(df),
            int(df["in_clean_sample"].sum()),
            output_path,
        )

    return df
