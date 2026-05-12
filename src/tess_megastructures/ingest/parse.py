"""A3: Parse TESS-SPOC DV XML files into per-TCE rows.

Replaces the existing ``parse_dv_reports.py`` with:

- Namespace-aware element lookup (no positional indexing).
- ``.get(key, default)`` for every optional XML attribute.
- Per-file error handling: malformed XML logs a warning, doesn't crash.
- Schema-stable Parquet output (explicit dtypes, fixed column order).

The parsed schema is documented in ``docs/data_dictionary.md``. New
fields can be added; existing fields must not change name or dtype.

Each XML file describes one TIC and may contain multiple TCE
(``planetResults``) elements. We emit one output row per TCE, with
star-level fields duplicated across rows from the same TIC.
"""

from __future__ import annotations

from pathlib import Path


# XML namespace used by SPOC DV reports.
DV_NAMESPACE = {"dv": "http://www.nasa.gov/2018/TESS/DV"}


def parse_dv_xml(xml_path: Path) -> list[dict]:
    """Parse a single DV XML file into TCE rows.

    Parameters
    ----------
    xml_path : Path
        Path to a ``.xml`` DV report.

    Returns
    -------
    list of dict
        One dict per TCE (``planetResults`` element) in the file.
        Empty list if the file has no TCEs (some targets have no
        detected signals).

    Raises
    ------
    Exception
        On malformed XML or missing required fields. Caller is
        responsible for catching and logging if running over many
        files; see :func:`parse_sector`.
    """
    raise NotImplementedError


def parse_sector(
    xml_dir: Path,
    output_path: Path,
    error_log_path: Path | None = None,
) -> dict[str, int]:
    """Parse all XML files in a directory into a single Parquet.

    Per-file errors are caught and logged; the run continues. The
    return value reports counts so callers can decide whether the
    error rate is acceptable.

    Parameters
    ----------
    xml_dir : Path
        Directory containing ``.xml`` files (recursively searched).
    output_path : Path
        Destination Parquet file.
    error_log_path : Path, optional
        Per-file errors written here as JSON lines.

    Returns
    -------
    dict
        Counts: ``files_total``, ``files_ok``, ``files_failed``,
        ``tces_extracted``.
    """
    raise NotImplementedError
