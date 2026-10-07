"""Loader for the CALNet eclipsing-binary catalog (Shan et al. 2025).

Shan Y., Chen J., Zhang Z., Wang L., Zou Z., Li M. (2025),
"Identifying eclipsing binary stars with TESS data based on a new hybrid
deep learning model." arXiv:2504.15875.

CALNet (a CNN+LSTM+CBAM model) was applied to TESS 2-minute cadence light
curves from Sectors 1-74; after manual visual inspection the authors report
9,351 new EBs. The published catalog file (``newecl.dat``, from the official
repository github.com/wangleon/CALNet) contains 10,531 unique TICs -- the new
EBs plus recovered known EBs -- as a fixed-width table keyed on TIC.

The ``Disp`` column carries sparse quality notes: ``SPLIT`` (blended / split
aperture), ``DUPLICATE`` (system catalogued twice), and ``ARTIFACT`` (flagged
spurious). We drop ARTIFACT rows (the authors mark them as not real) and
de-duplicate on TIC; every remaining row is an eclipsing binary.

Caveats for downstream use:
- This is a 2-minute-cadence-derived catalog; overlap with an FFI TCE sample
  may be modest (the 2-min targets are a pre-selected bright subset).
- CALNet's training set included Prsa+2022, so a fraction of these EBs overlap
  catalogs already in the cross-match; the marginal (new) contribution is what
  matters and is reported at the cross-match step.

The loader reads a LOCAL copy of ``newecl.dat`` (staged to the literature dir);
it does not download anything.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Disposition values that indicate a row should NOT be used as a real EB.
_DROP_DISPOSITIONS = {"ARTIFACT"}


def load(path: str | Path) -> pd.DataFrame:
    """Load the CALNet (Shan+2025) EB catalog.

    Returns a DataFrame with an int64 ``ticId`` column (de-duplicated),
    plus the catalog's ``disposition`` note where present. Rows flagged
    ARTIFACT by the authors are dropped.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CALNet catalog not found: {path}")

    # The file is a fixed-width table with a header row and a dashed ruler row.
    # Auto-inference misaligns on this file (many blank cells: Disp/HIP/TYC are
    # sparse), so use EXPLICIT column boundaries from the header ruler.
    # Field starts (0-indexed): TIC 0, m_TIC 11, Disp 21, RAJ2000 31, ...
    # We only need TIC and Disp.
    colspecs = [(0, 10), (21, 30)]
    names = ["ticId", "disposition"]
    raw = pd.read_fwf(path, colspecs=colspecs, names=names, skiprows=2)

    out = pd.DataFrame()
    out["ticId"] = pd.to_numeric(raw["ticId"], errors="coerce").astype("Int64")
    out["disposition"] = raw["disposition"].astype("string").str.strip()

    # Drop rows with no parseable TIC.
    n_raw = len(out)
    out = out[out["ticId"].notna()].copy()

    # Drop author-flagged artifacts.
    if "disposition" in out.columns:
        mask_drop = out["disposition"].isin(_DROP_DISPOSITIONS)
        n_artifact = int(mask_drop.sum())
        if n_artifact:
            out = out[~mask_drop].copy()
            logger.info("CALNet: dropped %d ARTIFACT-flagged rows", n_artifact)

    # De-duplicate on TIC (SPLIT/DUPLICATE entries can repeat a TIC).
    out["ticId"] = out["ticId"].astype("int64")
    out = out.drop_duplicates(subset="ticId").reset_index(drop=True)

    logger.info(
        "Loaded %d CALNet (Shan+2025) EBs (%d raw rows before dedup/artifact removal)",
        len(out),
        n_raw,
    )
    return out
