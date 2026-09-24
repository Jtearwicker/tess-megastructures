#!/usr/bin/env python3
"""Build the full EB-classifier training labels for a parsed TCE table.

Run from the repo root (after eb_labels.py is in src/tess_megastructures/annotate/):

    uv run python build_training_labels.py
    uv run python build_training_labels.py --tces <parsed.parquet> --out <labels.parquet>

Every TCE gets one label (eb, planet, fp, quarantine, unlabeled) plus the rule
that fired and provenance columns. Prints label sizes and the edge-case counts
that decide the labeling rules. Run 1 uses Prsa as the only EB catalog.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from tess_megastructures.annotate.eb_labels import add_training_labels, summarize_training_labels

ROOT = Path("/mnt/buf0/jearwicker/eb_data_pull")
DEFAULT_TCES = ROOT / "parsed/tce_dv_metrics_s1s2.parquet"
DEFAULT_CATALOGS = ROOT / "catalogs"
DEFAULT_OUT = ROOT / "parsed/tce_training_labels_s1s2.parquet"


def product_type(sectors) -> str:
    try:
        return "multi" if len(sectors) > 1 else "single"
    except TypeError:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build EB-classifier training labels.")
    ap.add_argument("--tces", type=Path, default=DEFAULT_TCES)
    ap.add_argument("--catalogs", type=Path, default=DEFAULT_CATALOGS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--tolerance", type=float, default=0.01)
    args = ap.parse_args()
    cat = args.catalogs

    tces = pd.read_parquet(args.tces)
    prsa = pd.read_parquet(cat / "vizier_prsa2022_t0.parquet", columns=["TIC", "Per"])
    prsa["ticId"] = pd.to_numeric(prsa["TIC"], errors="coerce").astype("Int64")
    prsa = prsa[prsa["ticId"].notna()].copy()
    planets = pd.read_parquet(cat / "exoarchive_pscomppars.parquet",
                              columns=["tic_id", "pl_orbper", "pl_name"])
    toi = pd.read_parquet(cat / "exoarchive_toi.parquet",
                          columns=["tid", "toi", "tfopwg_disp", "pl_orbper"])
    print(f"TCEs {len(tces):,} ({tces['tic_id'].nunique():,} TICs) | Prsa {len(prsa):,} | "
          f"planets {len(planets):,} | TOIs {len(toi):,}")

    out = add_training_labels(tces, prsa=prsa, planets=planets, toi=toi, tolerance=args.tolerance)
    if "sectors_observed" in out.columns:
        out["product_type"] = out["sectors_observed"].map(product_type)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)

    s = summarize_training_labels(out)
    print("\n=============== training labels ===============")
    for k, v in s["labels"].items():
        print(f"  {k:<11} {v:>7,}   ({100 * v / max(s['n_tces'], 1):4.1f}%)")
    print("\nrule that fired (label_reason):")
    for k, v in s["reasons"].items():
        print(f"  {k:<22} {v:>7,}")
    print("\nedge cases:")
    for k, v in s["edge_cases"].items():
        print(f"  {k:<32} {v:>6,}")
    print("\nplanet label sources:", s["planet_sources"])
    print("TOI disposition on unlabeled TCEs:", s["unlabeled_toi_disp"])
    if "product_type" in out.columns:
        print("\nlabel x product type:")
        print(pd.crosstab(out["label"], out["product_type"]).to_string())
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
