"""A1: Build the frozen parent stellar sample.

Produces ``parent_sample_v1.parquet``, one row per TIC, recording:

- TIC ID, RA, Dec
- Sectors in which the TIC was observed by SPOC FFI processing
- Total observation baseline (days)
- Stellar parameters (Teff, R*, log g, Tmag, distance, RUWE)
- Boolean flags from the cuts in ``configs/parent_sample_v1.yaml``:
    - ``passed_brightness_cut``
    - ``passed_parallax_cut``
    - ``passed_log_g_cut``
    - ``has_valid_stellar_params``
    - ``in_clean_sample``  (AND of all required cuts)

The parent sample is the v2 occurrence-rate denominator. Once frozen,
do not modify in place; create ``parent_sample_v2.parquet`` if cuts
need to change.

Inputs:

- TESS-SPOC FFI target lists per sector (from MAST).
- Doyle+24 cross-matched table (loaded via
  :mod:`tess_megastructures.catalogs.doyle2024`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_parent_sample(
    config: dict[str, Any],
    output_path: Path,
) -> None:
    """Build the parent sample and write to Parquet.

    Parameters
    ----------
    config : dict
        Parsed parent-sample config (from ``parent_sample_v1.yaml``).
    output_path : Path
        Destination Parquet file.
    """
    raise NotImplementedError
