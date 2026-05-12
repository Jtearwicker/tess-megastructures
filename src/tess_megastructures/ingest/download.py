"""A2: Download TESS-SPOC Data Validation XML files from MAST.

Replaces the existing ``generate_tce_data.py`` with:

- Resumable, parallel downloads
- Per-file integrity checks (XML is well-formed)
- Per-file failure tolerance (one bad file doesn't crash the run)
- State manifest updates so re-runs skip already-downloaded files

The MAST DV retrieval scripts are downloaded from:
``https://archive.stsci.edu/hlsps/tess-spoc/download_scripts/``

Each script contains many ``curl`` commands, one per data product. We
filter to ``.xml`` (the DV reports we care about) and execute these
in parallel via Python rather than shelling out to bash.
"""

from __future__ import annotations

from pathlib import Path


def download_sector_xml(
    sector_run: str,
    output_dir: Path,
    max_concurrent: int = 8,
    skip_existing: bool = True,
) -> dict[str, int]:
    """Download all DV XML files for a sector run.

    Parameters
    ----------
    sector_run : str
        Sector or multi-sector identifier, e.g. ``"s0055"`` or ``"s0056-s0069"``.
    output_dir : Path
        Where to write XML files (will mirror MAST's TIC-id-based path structure).
    max_concurrent : int
        Number of concurrent downloads. MAST tolerates ~16; default 8 to be polite.
    skip_existing : bool
        If True, skip files that already exist and pass integrity check.

    Returns
    -------
    dict
        Counts of: ``downloaded``, ``skipped``, ``failed``.
    """
    raise NotImplementedError
