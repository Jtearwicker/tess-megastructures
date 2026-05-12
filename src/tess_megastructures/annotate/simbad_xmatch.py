"""B4: SIMBAD cross-matching with persistent caching.

For every TIC in the master sample, query SIMBAD for its object types
and main identifier. Results are cached on disk keyed by TIC, so re-runs
don't re-hit SIMBAD.

The cache is a Parquet file at ``paths.simbad_cache_dir/simbad_cache.parquet``.
A TIC's cached entry is considered fresh for some configurable duration
(default 6 months); after that it's re-queried on next run.

Output columns added to the TCE table:

- ``simbad_main_id`` (str)
- ``simbad_otypes`` (str, space-separated)
- ``simbad_query_date`` (datetime)
- ``simbad_is_eb`` (bool)
- ``simbad_is_pulsator`` (bool)
- ``simbad_is_rotational`` (bool)
- ``simbad_is_yso`` (bool)
- ``simbad_is_variable`` (bool, True if any of the above)

Mapping from SIMBAD codes to categories is in
``configs/simbad_types.yaml``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def query_simbad_with_cache(
    tic_ids: list[int],
    cache_path: Path,
    max_age_days: int = 180,
    batch_size: int = 100,
) -> pd.DataFrame:
    """Query SIMBAD for a list of TICs, using and updating the cache.

    Parameters
    ----------
    tic_ids : list of int
        TICs to query.
    cache_path : Path
        Persistent cache parquet.
    max_age_days : int
        Re-query TICs whose cached entry is older than this.
    batch_size : int
        SIMBAD batch query size.

    Returns
    -------
    DataFrame
        One row per TIC, columns ``ticId``, ``simbad_main_id``,
        ``simbad_otypes``, ``simbad_query_date``.
    """
    raise NotImplementedError


def derive_simbad_flags(
    simbad_results: pd.DataFrame,
    types_config: dict,
) -> pd.DataFrame:
    """Translate SIMBAD otypes into category flags.

    Parameters
    ----------
    simbad_results : DataFrame
        Output of :func:`query_simbad_with_cache`.
    types_config : dict
        Parsed ``configs/simbad_types.yaml``.

    Returns
    -------
    DataFrame
        ``simbad_results`` with category boolean columns appended.
    """
    raise NotImplementedError
