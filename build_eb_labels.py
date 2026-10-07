#!/usr/bin/env python3
"""Build period-matched Prsa EB training labels for the parsed 2-min TCE table.

Run from the repo root, after dropping period_harmonics.py and eb_labels.py into
src/tess_megastructures/annotate/:

    uv run python build_eb_labels.py

Loads the parsed TCE table and the Prsa+2022 VizieR catalog, adds the
period-matched EB label (annotate/eb_labels.py) plus the TIC-internal harmonic
flag (annotate/period_harmonics.py), writes a labeled parquet, and prints yield
and Prsa coverage. The headline is membership vs period match: the gap is the
TCEs on EB-hosting TICs that a bare TIC-membership label would have mislabeled.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from tess_megastructures.annotate.eb_labels import add_period_matched_eb_labels
from tess_megastructures.annotate.period_harmonics import flag_period_harmonics

DEFAULT_TCES = Path("/mnt/buf0/jearwicker/eb_data_pull/parsed/tce_dv_metrics_s1s2.parquet")
DEFAULT_PRSA = Path("/mnt/buf0/jearwicker/eb_data_pull/catalogs/vizier_prsa2022_t0.parquet")
DEFAULT_OUT = Path("/mnt/buf0/jearwicker/eb_data_pull/parsed/tce_labels_s1s2.parquet")


def load_prsa(path: Path) -> pd.DataFrame:
    """Load the Prsa VizieR parquet and add an int64 ticId for cross-matching."""
    df = pd.read_parquet(path)
    df["ticId"] = pd.to_numeric(df["TIC"], errors="coerce").astype("Int64")
    df = df[df["ticId"].notna()].copy()
    df["ticId"] = df["ticId"].astype("int64")
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description="Build period-matched Prsa EB labels.")
    ap.add_argument("--tces", type=Path, default=DEFAULT_TCES)
    ap.add_argument("--prsa", type=Path, default=DEFAULT_PRSA)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--tolerance", type=float, default=0.01)
    args = ap.parse_args()

    tces = pd.read_parquet(args.tces)
    prsa = load_prsa(args.prsa)
    print(f"TCE table : {len(tces):,} rows, {tces['tic_id'].nunique():,} TICs  <- {args.tces}")
    print(f"Prsa+2022 : {len(prsa):,} EBs, {prsa['ticId'].nunique():,} TICs   <- {args.prsa}")

    labeled = add_period_matched_eb_labels(tces, prsa, tolerance=args.tolerance)
    labeled = flag_period_harmonics(labeled)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    labeled.to_parquet(args.out, index=False)

    n = len(labeled)
    lab = labeled["label_prsa_eb"]
    prsa_tics = set(prsa["ticId"])
    on_tic = labeled["tic_id"].isin(prsa_tics)
    present = set(labeled.loc[on_tic, "tic_id"])
    matched = set(labeled.loc[lab, "tic_id"])

    print("\n================= EB label yield =================")
    print(f"TCEs total                          : {n:,}")
    print(f"  period-matched EB (label_prsa_eb) : {int(lab.sum()):,}")
    print(f"  on a Prsa TIC (membership)        : {int(on_tic.sum()):,}")
    print(f"  on a Prsa TIC, NOT period-matched : {int(on_tic.sum()) - int(lab.sum()):,}"
          "  <- mislabeled by TIC membership alone")
    print("\nHarmonic breakdown of positives (label_prsa_ratio):")
    for r, name in [(1.0, "1:1  same period"),
                    (2.0, "2:1  TCE = 2x catalog"),
                    (0.5, "1:2  TCE = catalog/2 (EB found at half period)")]:
        print(f"  {name:46} {int((labeled['label_prsa_ratio'] == r).sum()):,}")
    print("\nPrsa coverage in this TCE set:")
    print(f"  Prsa TICs appearing as a TCE       : {len(present):,}")
    pct = 100 * len(matched) / max(len(present), 1)
    print(f"  of those, with a period-matched TCE: {len(matched):,}  ({pct:.0f}%)")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
