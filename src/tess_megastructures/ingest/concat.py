"""A5: Concatenate per-sector TCE Parquets into the master TCE table.

Reads all per-sector ``tces_{sector_run}.parquet`` files and concatenates
them into a single ``tces_master.parquet`` -- the Definition-B TCE
population aggregated across all sectors.

All per-sector files share the schema emitted by parse.py, so this is a
straight row-wise concatenation. Uses an outer join on columns defensively
(so a future schema addition in one sector doesn't crash the concat --
missing columns fill with null rather than raising).

CLI (called by workflow/rules/ingest.smk :: concat_master_tces):
    python -m tess_megastructures.ingest.concat \\
        --inputs tces_s0036.parquet ... --output tces_master.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def concat_sectors(input_paths: list[Path], output_path: Path) -> dict[str, int]:
    """Concatenate per-sector Parquets into one master table.

    Returns counts: ``n_files``, ``n_tces``, ``n_tics``.
    """
    if not input_paths:
        raise ValueError("no input parquet files given")

    frames = []
    for p in input_paths:
        df = pd.read_parquet(p)
        frames.append(df)

    # outer join on columns: robust to a sector having extra/missing cols.
    # (All current sectors share schema, so this is a no-op union in practice.)
    master = pd.concat(frames, ignore_index=True, join="outer", sort=False)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    master.to_parquet(output_path, index=False)

    n_tics = master["tic_id"].nunique() if "tic_id" in master.columns else -1
    return {"n_files": len(input_paths), "n_tces": len(master), "n_tics": n_tics}


def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Concatenate per-sector TCE parquets.")
    ap.add_argument("--inputs", nargs="+", required=True, type=Path,
                    help="per-sector parquet files")
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args(argv)

    try:
        counts = concat_sectors(args.inputs, args.output)
    except Exception as e:
        print(f"ERROR: concat failed: {e}", file=sys.stderr)
        return 1

    print(
        f"master: {counts['n_files']} sectors -> {counts['n_tces']} TCEs, "
        f"{counts['n_tics']} unique TICs",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
