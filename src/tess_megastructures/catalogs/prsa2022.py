"""prsa2022 catalog loader.

Prsa et al. 2022, "TESS Eclipsing Binary Stars. I. Sectors 1-26"
(ApJS 258:16). VizieR J/ApJS/258/16. 4,584 validated eclipsing binaries
from TESS 2-min cadence. VETTED -> used as a catalog EB flag.

The catalog is downloaded and cached by ``scripts/download_catalogs.py``
to ``<literature_dir>/prsa2022_ebs.csv`` (TIC column: ``TIC``).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# VizieR column holding the TIC identifier.
_TIC_COL = "TIC"


def load(path: Path) -> pd.DataFrame:
    """Load the prsa2022 catalog from disk into a tidy DataFrame.

    Parameters
    ----------
    path : Path
        Path to the cached CSV (``prsa2022_ebs.csv``).

    Returns
    -------
    DataFrame
        The catalog with an added int64 ``ticId`` column for cross-matching.
        Rows with an unparseable TIC are dropped.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Prsa+2022 catalog not found: {path}. Run scripts/download_catalogs.py first."
        )
    df = pd.read_csv(path)
    if _TIC_COL not in df.columns:
        raise KeyError(f"{_TIC_COL!r} not in {path}; columns: {list(df.columns)}")

    df["ticId"] = pd.to_numeric(df[_TIC_COL], errors="coerce").astype("Int64")
    before = len(df)
    df = df[df["ticId"].notna()].copy()
    df["ticId"] = df["ticId"].astype("int64")
    if len(df) < before:
        logger.warning("Prsa+2022: dropped %d rows with bad TIC", before - len(df))
    logger.info("Loaded %d Prsa+2022 EBs", len(df))
    return df
