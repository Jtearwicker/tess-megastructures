"""Build the v1 TCE sample from parsed sector Parquets.

Driver script that wires together the subsystem-A pieces plus the
subsystem-B diagnostic flags:

    parsed sectors  -->  build_tce_sample  -->  tce_sample_v1.parquet
        ^                       ^
        |                       |
    parser output       Doyle+24 enrichment + diagnostic flags

This is a thin glue runner, not a tested module — its job is to read paths
from configs, call the already-tested module functions, write the output,
and print a summary.

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
from tess_megastructures.catalogs.kostov2025 import (
    load as load_kostov2025_vetted,
)
from tess_megastructures.catalogs.kostov2025 import (
    load_unvetted as load_kostov2025_unvetted,
)
from tess_megastructures.catalogs.oddo2025 import load as load_oddo2025
from tess_megastructures.catalogs.prsa2022 import load as load_prsa2022
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

    # --- EB catalogs for cross-match (graceful: None if path unset/missing)
    def _maybe_load(key, loader, label):
        fp = paths.get(key)
        if not fp or str(fp).startswith("/path/to"):
            logger.warning("%s path not set in paths.yaml (%s); skipping", label, key)
            return None
        try:
            df_cat = loader(Path(fp))
            logger.info("%s: %d rows", label, len(df_cat))
            return df_cat
        except FileNotFoundError:
            logger.warning("%s file not found at %s; skipping", label, fp)
            return None

    prsa = _maybe_load("prsa2022_catalog", load_prsa2022, "Prsa+2022")
    kostov_vetted = _maybe_load(
        "kostov2025_vetted_catalog", load_kostov2025_vetted, "Kostov+2025 vetted"
    )
    kostov_unvetted = _maybe_load(
        "kostov2025_unvetted_catalog", load_kostov2025_unvetted, "Kostov+2025 unvetted"
    )
    oddo = _maybe_load("oddo2025_catalog", load_oddo2025, "Oddo+2025")

    # --- build the TCE sample
    output_filename = sample_config.get("output", {}).get("filename", "tce_sample_v1.parquet")
    output_path = output_dir / output_filename

    logger.info("building TCE sample -> %s", output_path)
    df = build_tce_sample(
        parsed_paths=parsed_paths,
        config=sample_config,
        output_path=output_path,
        doyle=doyle,
        prsa=prsa,
        kostov_vetted=kostov_vetted,
        kostov_unvetted=kostov_unvetted,
        oddo=oddo,
    )

    if df.empty:
        logger.warning("Resulting TCE sample is empty.")
        return 1

    # --- summary
    n_total = len(df)
    n_with_doyle = int(df["has_doyle_params"].sum())
    n_clean = int(df["in_clean_sample"].sum())

    def _bool_count(col: str) -> int:
        s = df[col]
        return int(s.sum() if s.dtype == "bool" else s.fillna(False).astype(bool).sum())

    cut_cols = [c for c in df.columns if c.startswith("passed_")]
    flag_cols = [c for c in df.columns if c.startswith("flag_")]

    print()
    print("========== TCE sample build summary ==========")
    print(f"  output:                  {output_path}")
    print(f"  rows (TCEs):             {n_total:,}")
    print(f"  unique TICs:             {df['tic_id'].nunique():,}")
    print(f"  Doyle match:             {n_with_doyle:,}  ({n_with_doyle / n_total * 100:.1f}%)")
    print(f"  in_clean_sample:         {n_clean:,}  ({n_clean / n_total * 100:.1f}%)")

    print("  per-cut pass counts (raw, before AND):")
    for col in cut_cols:
        n = _bool_count(col)
        print(f"    {col:32s}  {n:>6,}  ({n / n_total * 100:.1f}%)")

    if flag_cols:
        print("  diagnostic flags (True = suspicious):")
        for col in flag_cols:
            n = _bool_count(col)
            print(f"    {col:32s}  {n:>6,}  ({n / n_total * 100:.1f}%)")
        if "any_diagnostic_flag" in df.columns:
            n_any = _bool_count("any_diagnostic_flag")
            n_unflagged = n_total - n_any
            print(
                f"    {'-> unflagged (no flags set)':32s}  "
                f"{n_unflagged:>6,}  ({n_unflagged / n_total * 100:.1f}%)"
            )

    if "run_type" in df.columns:
        print("  run_type breakdown:")
        for rt, n in df["run_type"].value_counts().items():
            print(f"    {str(rt):32s}  {n:>6,}")
    print("==============================================")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
