"""kostov2025 catalog loader.

Kostov et al. 2025, "The TESS Ten Thousand Catalog" (ApJS 279:50).
VizieR J/ApJS/279/50. Detected in TESS FFI data, sectors 1-82.

Two populations, with different roles in the pipeline:

- VETTED: 10,001 uniformly-vetted, validated EBs (VizieR tables 0+1,
  combined by the downloader into ``kostov2025_vetted_ebs.csv``).
  Used as a catalog EB flag.
- UNVETTED: ~872,720 neural-network candidates (VizieR table 2,
  ``kostov2025_unvetted_candidates.csv``). The paper notes 56-86% of NN
  candidates are NOT EBs, so this is used as an ANNOTATION only -- it
  marks catalog membership but never gates candidate selection.

Both files have TIC column ``TIC``. Cached by scripts/download_catalogs.py.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_TIC_COL = "TIC"


def _load_with_ticid(path: Path, label: str) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Kostov+2025 {label} catalog not found: {path}. "
            "Run scripts/download_catalogs.py first."
        )
    df = pd.read_csv(path)
    if _TIC_COL not in df.columns:
        raise KeyError(f"{_TIC_COL!r} not in {path}; columns: {list(df.columns)}")
    df["ticId"] = pd.to_numeric(df[_TIC_COL], errors="coerce").astype("Int64")
    before = len(df)
    df = df[df["ticId"].notna()].copy()
    df["ticId"] = df["ticId"].astype("int64")
    if len(df) < before:
        logger.warning("Kostov+2025 %s: dropped %d rows with bad TIC", label, before - len(df))
    logger.info("Loaded %d Kostov+2025 %s rows", len(df), label)
    return df


def load(path: Path) -> pd.DataFrame:
    """Load the Kostov+2025 VETTED catalog (the 10,001).

    This is the default ``load`` (matching the other catalog loaders'
    contract): returns the vetted EBs with an int64 ``ticId`` column.

    Parameters
    ----------
    path : Path
        Path to ``kostov2025_vetted_ebs.csv``.
    """
    return _load_with_ticid(path, "vetted")


def load_unvetted(path: Path) -> pd.DataFrame:
    """Load the Kostov+2025 UNVETTED candidate list (~873k, annotation only).

    Parameters
    ----------
    path : Path
        Path to ``kostov2025_unvetted_candidates.csv``.
    """
    return _load_with_ticid(path, "unvetted")
