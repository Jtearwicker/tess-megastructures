"""C2: Generate per-candidate vetting packages.

For each candidate in the vetting queue, generate:

1. The DV mini report PDF (``dvm``) from MAST.
2. The full DV summary PDF (``dvs``) from MAST.
3. A phase-folded light curve at the reported orbital period.
4. A multi-sector stacked light curve.
5. A summary card (HTML) with all metrics, catalog flags, SIMBAD info,
   and external resource links (SIMBAD, ExoFOP, ZTF, ASAS-SN).
6. A Wright+16 signature checklist for the vetter.

Packages are written to ``paths.vetting_packages_dir/<candidate_id>/``.

Steps 1-2 use the curl URL pattern documented in the predecessor's
notebook. Steps 3-4 require downloading FFI light curves; for v1's
limited candidate count (~hundreds) this is tractable.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def generate_vetting_package(
    candidate_row: pd.Series,
    output_dir: Path,
) -> Path:
    """Generate the full review package for one candidate.

    Parameters
    ----------
    candidate_row : Series
        One row from the vetting queue with all annotated columns.
    output_dir : Path
        Where to write package files. Will be created if missing.

    Returns
    -------
    Path
        Path to the package directory.
    """
    raise NotImplementedError


def generate_all_packages(
    queue: pd.DataFrame,
    base_dir: Path,
    skip_existing: bool = True,
) -> None:
    """Generate packages for every candidate in the vetting queue."""
    raise NotImplementedError
