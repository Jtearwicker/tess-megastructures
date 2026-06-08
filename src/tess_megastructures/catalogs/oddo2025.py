"""oddo2025 catalog loader.

Oddo et al. 2025, "A Catalog of M&M Eclipsing Binaries with TESS"
(ApJ 996, 82; DOI 10.3847/1538-4357/ae0c0f). 1,292 low-mass (M+M)
short-period eclipsing binaries. VETTED -> used as a catalog EB flag.

Not on VizieR at time of writing; the AAS machine-readable table (Table 1)
is downloaded manually from the published article and cached to
``<literature_dir>/oddo2025_table1_mrt.txt``. The MRT has a byte-by-byte
header; astropy reads it natively. TIC column: ``TIC`` (bytes 1-9).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_TIC_COL = "TIC"


def load(path: Path) -> pd.DataFrame:
    """Load the Oddo+2025 catalog (AAS MRT) into a tidy DataFrame.

    Parameters
    ----------
    path : Path
        Path to the cached machine-readable table (``oddo2025_table1_mrt.txt``).

    Returns
    -------
    DataFrame
        The catalog with an added int64 ``ticId`` column for cross-matching.
        Rows with an unparseable TIC are dropped.
    """
    from astropy.io import ascii as ascii_io

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Oddo+2025 catalog not found: {path}. "
            "Download Table 1 (MRT) from the published article and cache it there."
        )
    table = ascii_io.read(str(path), format="mrt")
    df = table.to_pandas()
    if _TIC_COL not in df.columns:
        raise KeyError(f"{_TIC_COL!r} not in {path}; columns: {list(df.columns)}")

    df["ticId"] = pd.to_numeric(df[_TIC_COL], errors="coerce").astype("Int64")
    before = len(df)
    df = df[df["ticId"].notna()].copy()
    df["ticId"] = df["ticId"].astype("int64")
    if len(df) < before:
        logger.warning("Oddo+2025: dropped %d rows with bad TIC", before - len(df))
    logger.info("Loaded %d Oddo+2025 M+M EBs", len(df))
    return df
