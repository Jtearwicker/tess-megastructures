"""Build the v1 TCE sample from parsed sector Parquets.

Driver script that wires together the three subsystem-A pieces:

    parsed sectors  -->  build_tce_sample  -->  tce_sample_v1.parquet
        ^                       ^
        |                       |
    parser output       Doyle+24 enrichment

This is a thin glue runner, not a tested module — its job is to read paths
from configs, call the already-tested module functions, write the output,
and print a summary. As subsystem B comes online (annotation), this driver
will grow; for now it's a single-step build.

Usage
-----
    uv run python scripts/build_tce_sample.py

Paths come from ``configs/paths.yaml`` (per-machine) and the sample config
from ``configs/tce_sample_v1.yaml``. Both must exist on the machine you
run this on. The parsed-sector Parquets must already be present in the
``processed_data_dir`` (run the parser first).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import yaml

from tess_megastructures.catalogs.doyle2024 import load_doyle2024
from tess_megastructures.ingest.tce_sample import (
    build_tce_sample,
    find_parsed_sectors,
)
from tess_megastructures.utils.paths import configs_dir, load_paths

logger = logging.getLogger("build_tce_sample")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # --- paths
    paths = load_paths()
    processed_dir = Path(paths["processed_data_dir"])
    output_dir = Path(paths["output_dir"])
    doyle_path = Path(paths["doyle2024_catalog"])

    # --- sample config
    sample_config_path = configs_dir() / "tce_sample_v1.yaml"
    with open(sample_config_path) as f:
        sample_config = yaml.safe_load(f)
    logger.info("loaded sample config: %s", sample_config_path)

    # --- find parsed sector Parquets
    parsed_paths = find_parsed_sectors(processed_dir)
    if not parsed_paths:
        logger.error(
            "No parsed sector Parquets found in %s (expected files like "
            "tce_dv_metrics_*.parquet). Run the parser first.",
            processed_dir,
        )
        return 1
    logger.info("found %d parsed sector file(s):", len(parsed_paths))
    for p in parsed_paths:
        logger.info("  - %s", p.name)

    # --- Doyle catalog
    logger.info("loading Doyle+24 catalog from %s", doyle_path)
    doyle = load_doyle2024(doyle_path)
    logger.info("Doyle catalog: %d targets", len(doyle))

    # --- build the TCE sample
    output_filename = sample_config.get("output", {}).get("filename", "tce_sample_v1.parquet")
    output_path = output_dir / output_filename

    logger.info("building TCE sample -> %s", output_path)
    df = build_tce_sample(
        parsed_paths=parsed_paths,
        config=sample_config,
        output_path=output_path,
        doyle=doyle,
    )

    if df.empty:
        logger.warning("Resulting TCE sample is empty.")
        return 1

    # --- summary
    n_total = len(df)
    n_with_doyle = int(df["has_doyle_params"].sum())
    n_clean = int(df["in_clean_sample"].sum())

    cut_cols = [c for c in df.columns if c.startswith("passed_")]
    cut_summary = {
        c: (
            int(df[c].sum())
            if df[c].dtype == "bool"
            else int(df[c].fillna(False).astype(bool).sum())
        )
        for c in cut_cols
    }

    print()
    print("========== TCE sample build summary ==========")
    print(f"  output:                  {output_path}")
    print(f"  rows (TCEs):             {n_total:,}")
    print(f"  unique TICs:             {df['tic_id'].nunique():,}")
    print(f"  Doyle match:             {n_with_doyle:,}  ({n_with_doyle / n_total * 100:.1f}%)")
    print(f"  in_clean_sample:         {n_clean:,}  ({n_clean / n_total * 100:.1f}%)")
    print("  per-cut pass counts (raw, before AND):")
    for col, n in cut_summary.items():
        print(f"    {col:32s}  {n:>6,}  ({n / n_total * 100:.1f}%)")
    if "run_type" in df.columns:
        print("  run_type breakdown:")
        for rt, n in df["run_type"].value_counts().items():
            print(f"    {str(rt):32s}  {n:>6,}")
    print("==============================================")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
