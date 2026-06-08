"""Download reference EB catalogs and cache them locally.

Fetches the vetted eclipsing-binary catalogs used for the catalog cross-match
stage and caches them as CSVs under ``literature_dir`` (from configs/paths.yaml).
Run once; the loaders then read the cached CSVs.

Catalogs
--------
- Prsa+2022   (J/ApJS/258/16)  4,584 EBs, sectors 1-26 2-min.  VETTED.
- Kostov+2025 (J/ApJS/279/50)  the "TESS Ten Thousand". VizieR returns 3 tables:
    table 0: 7,936 newly-discovered vetted EBs   -> VETTED
    table 1: 2,065 known/recovered vetted EBs    -> VETTED
       (0 + 1 = the 10,001 uniformly-vetted catalog)
    table 2: 872,720 unvetted NN candidates      -> UNVETTED (annotation only)
- Oddo+2025   (arXiv 2508.13941) 1,292 M+M EBs.   VETTED. (not on VizieR yet)

Output CSVs (under literature_dir)
----------------------------------
- prsa2022_ebs.csv                    vetted (Prsa)
- kostov2025_vetted_ebs.csv           vetted (Kostov tables 0+1 combined, 10,001)
- kostov2025_unvetted_candidates.csv  unvetted (Kostov table 2, ~873k) -- annotation only

VizieR table indices are pinned explicitly (NOT "largest table wins"), because
for Kostov the largest table is the UNVETTED one -- the opposite of what we want
to flag on.

Usage
-----
    uv run python scripts/download_catalogs.py --inspect   # report only, no cache
    uv run python scripts/download_catalogs.py             # fetch + cache
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

logger = logging.getLogger("download_catalogs")

PRSA2022_VIZIER = "J/ApJS/258/16"
KOSTOV2025_VIZIER = "J/ApJS/279/50"
# Oddo+2025 -- recent; VizieR designation TBD. Handle separately when available.
ODDO2025_VIZIER = None

# Kostov table roles, pinned by index (confirmed via --inspect 2026-06-08):
#   0 -> vetted (new), 1 -> vetted (recovered), 2 -> unvetted candidates
KOSTOV_VETTED_TABLE_IDX = (0, 1)
KOSTOV_UNVETTED_TABLE_IDX = 2


def _paths_literature_dir() -> Path:
    here = Path(__file__).resolve()
    repo_root = here.parent.parent
    paths_fp = repo_root / "configs" / "paths.yaml"
    if not paths_fp.exists():
        raise FileNotFoundError(f"configs/paths.yaml not found at {paths_fp}")
    with open(paths_fp) as f:
        paths = yaml.safe_load(f)
    lit = paths.get("literature_dir")
    if not lit or str(lit).startswith("/path/to"):
        raise ValueError(
            "literature_dir in configs/paths.yaml is unset or still a placeholder; "
            "edit it to a real directory (e.g. /mnt/buf0/jearwicker/literature)."
        )
    return Path(lit)


def _fetch_vizier(designation: str, label: str):
    """Fetch all tables for a VizieR designation. Returns a list of astropy Tables."""
    from astroquery.vizier import Vizier

    v = Vizier(columns=["**"])
    v.ROW_LIMIT = -1
    logger.info("[%s] querying VizieR %s ...", label, designation)
    catalogs = v.get_catalogs(designation)
    logger.info("[%s] VizieR returned %d table(s)", label, len(catalogs))
    for i, tbl in enumerate(catalogs):
        logger.info("[%s]   table[%d]: %d rows", label, i, len(tbl))
    return list(catalogs)


def _write_csv(tbl, out_fp: Path, label: str) -> None:
    out_fp.parent.mkdir(parents=True, exist_ok=True)
    df = tbl.to_pandas()
    df.to_csv(out_fp, index=False)
    logger.info("[%s] cached %d rows -> %s", label, len(df), out_fp)


def _write_csv_df(df, out_fp: Path, label: str) -> None:
    out_fp.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_fp, index=False)
    logger.info("[%s] cached %d rows -> %s", label, len(df), out_fp)


def fetch_prsa(lit_dir: Path, inspect_only: bool) -> None:
    try:
        tables = _fetch_vizier(PRSA2022_VIZIER, "Prsa2022")
    except Exception as e:  # noqa: BLE001
        logger.error("[Prsa2022] VizieR fetch failed: %s", e)
        return
    if not tables:
        logger.warning("[Prsa2022] no tables returned")
        return
    tbl = tables[0]
    logger.info("[Prsa2022] %d rows, columns: %s", len(tbl), list(tbl.colnames))
    if inspect_only:
        logger.info("[Prsa2022] --inspect: not caching.")
        return
    _write_csv(tbl, lit_dir / "prsa2022_ebs.csv", "Prsa2022")


def fetch_kostov(lit_dir: Path, inspect_only: bool) -> None:
    try:
        tables = _fetch_vizier(KOSTOV2025_VIZIER, "Kostov2025")
    except Exception as e:  # noqa: BLE001
        logger.error("[Kostov2025] VizieR fetch failed: %s", e)
        return
    n = len(tables)
    if n < 3:
        logger.error(
            "[Kostov2025] expected 3 tables (got %d); VizieR layout may have "
            "changed. Inspect columns and update KOSTOV_*_TABLE_IDX.",
            n,
        )
        return

    import pandas as pd

    vetted_parts = []
    for idx in KOSTOV_VETTED_TABLE_IDX:
        t = tables[idx]
        logger.info(
            "[Kostov2025] vetted table[%d]: %d rows, columns: %s",
            idx,
            len(t),
            list(t.colnames),
        )
        vetted_parts.append(t.to_pandas())

    unv = tables[KOSTOV_UNVETTED_TABLE_IDX]
    logger.info(
        "[Kostov2025] unvetted table[%d]: %d rows, columns: %s",
        KOSTOV_UNVETTED_TABLE_IDX,
        len(unv),
        list(unv.colnames),
    )

    if inspect_only:
        logger.info("[Kostov2025] --inspect: not caching.")
        return

    vetted = pd.concat(vetted_parts, ignore_index=True)
    n_unique = vetted["TIC"].nunique()
    logger.info(
        "[Kostov2025] vetted combined: %d rows, %d unique TICs",
        len(vetted),
        n_unique,
    )
    _write_csv_df(vetted, lit_dir / "kostov2025_vetted_ebs.csv", "Kostov2025-vetted")
    _write_csv(unv, lit_dir / "kostov2025_unvetted_candidates.csv", "Kostov2025-unvetted")


def main(argv: list[str]) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description="Download reference EB catalogs.")
    ap.add_argument(
        "--inspect",
        action="store_true",
        help="Report catalog structure without caching to disk.",
    )
    args = ap.parse_args(argv)

    lit_dir = _paths_literature_dir()
    logger.info("literature_dir = %s", lit_dir)

    fetch_prsa(lit_dir, args.inspect)
    fetch_kostov(lit_dir, args.inspect)

    if ODDO2025_VIZIER is None:
        logger.warning(
            "[Oddo2025] no VizieR designation set (arXiv 2508.13941, recent). "
            "Skipping; add its table manually from the journal when available."
        )

    logger.info("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
