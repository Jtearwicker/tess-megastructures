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
- Oddo+2025   (arXiv 2508.13941) 1,292 M+M EBs.  VETTED. Not on VizieR yet, so
    fetched from the arXiv e-print source tarball (which contains the AAS
    machine-readable table). Use --oddo-inspect first to confirm the table
    format, then a real fetch caches it.

Output CSVs (under literature_dir)
----------------------------------
- prsa2022_ebs.csv                    vetted (Prsa)
- kostov2025_vetted_ebs.csv           vetted (Kostov tables 0+1 combined, 10,001)
- kostov2025_unvetted_candidates.csv  unvetted (Kostov table 2, ~873k) -- annotation only
- oddo2025_mm_ebs.csv                 vetted (Oddo, 1,292 M+M EBs)

Usage
-----
    uv run python scripts/download_catalogs.py --inspect        # Vizier report only
    uv run python scripts/download_catalogs.py                  # fetch + cache Prsa/Kostov
    uv run python scripts/download_catalogs.py --oddo-inspect   # report Oddo e-print tables
    uv run python scripts/download_catalogs.py --oddo           # fetch + cache Oddo
"""

from __future__ import annotations

import argparse
import logging
import sys
import tarfile
import urllib.request
from pathlib import Path

import yaml

logger = logging.getLogger("download_catalogs")

PRSA2022_VIZIER = "J/ApJS/258/16"
KOSTOV2025_VIZIER = "J/ApJS/279/50"

# Oddo+2025 -- not on VizieR; fetched from the arXiv e-print source tarball.
ODDO2025_ARXIV_ID = "2508.13941"

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


# =====================================================================
# VizieR catalogs (Prsa, Kostov)
# =====================================================================


def _fetch_vizier(designation: str, label: str):
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
    logger.info(
        "[Kostov2025] vetted combined: %d rows, %d unique TICs",
        len(vetted),
        vetted["TIC"].nunique(),
    )
    _write_csv_df(vetted, lit_dir / "kostov2025_vetted_ebs.csv", "Kostov2025-vetted")
    _write_csv(unv, lit_dir / "kostov2025_unvetted_candidates.csv", "Kostov2025-unvetted")


# =====================================================================
# Oddo 2025 -- arXiv e-print source tarball (AAS machine-readable table)
# =====================================================================


def _download_arxiv_eprint(arxiv_id: str, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    out = dest_dir / f"arxiv_{arxiv_id.replace('.', '_')}.tar.gz"
    logger.info("[Oddo2025] downloading arXiv e-print %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "tess-megastructures/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    out.write_bytes(data)
    logger.info("[Oddo2025] downloaded %d bytes -> %s", len(data), out)
    return out


def _list_eprint_tables(tar_path: Path) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    try:
        with tarfile.open(tar_path, "r:*") as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                name = m.name.lower()
                if name.endswith((".mrt", ".dat", ".txt", ".tsv", ".csv")) or "table" in name:
                    f = tf.extractfile(m)
                    if f is not None:
                        out.append((m.name, f.read()))
    except tarfile.ReadError:
        logger.warning("[Oddo2025] not a tarball; inspect %s manually", tar_path)
    return out


def _try_parse_table(name: str, content: bytes):
    from astropy.table import Table

    tmp = Path("/tmp") / Path(name).name
    tmp.write_bytes(content)
    for fmt in ("ascii.mrt", "ascii.cds", "ascii"):
        try:
            t = Table.read(str(tmp), format=fmt)
            if len(t.colnames) >= 1 and len(t) > 0:
                return t, fmt
        except Exception:  # noqa: BLE001
            continue
    return None, None


def _find_tic_col(colnames: list[str]) -> str | None:
    for c in colnames:
        if c.lower().replace(" ", "").replace("_", "") in {"tic", "ticid"}:
            return c
    for c in colnames:
        if "tic" in c.lower():
            return c
    return None


def fetch_oddo(lit_dir: Path, inspect_only: bool) -> None:
    work = lit_dir / "_oddo_eprint"
    try:
        tar = _download_arxiv_eprint(ODDO2025_ARXIV_ID, work)
    except Exception as e:  # noqa: BLE001
        logger.error("[Oddo2025] download failed: %s", e)
        return

    tables = _list_eprint_tables(tar)
    if not tables:
        logger.warning("[Oddo2025] no candidate table files in e-print; extract %s manually.", tar)
        return

    logger.info("[Oddo2025] found %d candidate table file(s):", len(tables))
    parsed = []
    for name, content in tables:
        t, fmt = _try_parse_table(name, content)
        if t is not None:
            tic_col = _find_tic_col(list(t.colnames))
            logger.info(
                "[Oddo2025]   %s (%d bytes): PARSED as %s, %d rows, cols=%s, TIC=%r",
                name,
                len(content),
                fmt,
                len(t),
                list(t.colnames),
                tic_col,
            )
            if tic_col is not None:
                parsed.append((name, t, tic_col, len(t)))
        else:
            head = "\n".join(content.decode("utf-8", "replace").splitlines()[:8])
            logger.info(
                "[Oddo2025]   %s (%d bytes): could not auto-parse; head:\n%s",
                name,
                len(content),
                head,
            )

    if inspect_only:
        logger.info("[Oddo2025] --oddo-inspect: not caching.")
        return

    if not parsed:
        logger.error("[Oddo2025] no parseable table with a TIC column; not caching.")
        return

    # cache the largest parseable TIC table (the catalog membership table)
    name, t, tic_col, _ = max(parsed, key=lambda x: x[3])
    df = t.to_pandas()
    logger.info("[Oddo2025] caching %r (%d rows, TIC col %r)", name, len(df), tic_col)
    _write_csv_df(df, lit_dir / "oddo2025_mm_ebs.csv", "Oddo2025")


def main(argv: list[str]) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description="Download reference EB catalogs.")
    ap.add_argument("--inspect", action="store_true", help="Vizier report only (Prsa/Kostov).")
    ap.add_argument(
        "--oddo-inspect", action="store_true", help="Report Oddo e-print tables, no cache."
    )
    ap.add_argument("--oddo", action="store_true", help="Fetch + cache Oddo only.")
    args = ap.parse_args(argv)

    lit_dir = _paths_literature_dir()
    logger.info("literature_dir = %s", lit_dir)

    if args.oddo_inspect:
        fetch_oddo(lit_dir, inspect_only=True)
        logger.info("done.")
        return 0
    if args.oddo:
        fetch_oddo(lit_dir, inspect_only=False)
        logger.info("done.")
        return 0

    # default / --inspect: Prsa + Kostov (Vizier)
    fetch_prsa(lit_dir, args.inspect)
    fetch_kostov(lit_dir, args.inspect)
    logger.info("Oddo not fetched in this mode. Use --oddo-inspect then --oddo to add it.")
    logger.info("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
