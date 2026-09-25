#!/usr/bin/env python3
"""Add Doyle+24 RUWE and the Gaia DR3 EB holdout to a built training release.

Run from the repo root after build_release.py:

    uv run python build_gaia_supplement.py --release /mnt/buf0/jearwicker/eb_training/v1

Writes <release>/supplementary/gaia_ruwe_holdout.parquet (one row per TCE; join to
tces_labeled.parquet on xml_filename + planet_number), adds a section to
README.md, and updates manifest.tsv for the files it wrote or changed.

RUWE comes from Doyle+24 (Vizier J/MNRAS/529/1802), the source MegaMiner already
uses (doyle_ruwe), so the classifier sees the values it will see in production.
Gaia DR3 EBs (gaiadr3.vari_eclipsing_binary, Mowlavi+2023) are matched through the
Doyle+24 Gaia DR3 id. Periods (1/frequency) are fetched from the Gaia archive for
the matched stars only. The Gaia EB columns are an independent holdout for
evaluation and must never be used as training labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

from tess_megastructures.annotate.period_harmonics import EB_LABEL_TARGETS, matched_ratio
from tess_megastructures.catalogs import doyle2024 as d24

DEFAULT_DOYLE = Path("/mnt/primary/TESS/catalogs/doyle2024/targets.dat.gz")
DEFAULT_GAIA_EB = Path("/mnt/buf0/jearwicker/eb_data_pull/catalogs/gaia_dr3_eclipsing_binaries.parquet")
OUT_NAME = "supplementary/gaia_ruwe_holdout.parquet"
README_MARK = "## Supplementary: RUWE and Gaia DR3 EB holdout"
BATCH = 500

TCE_COLS = ["xml_filename", "planet_number", "tic_id", "orbital_period_days", "label", "on_eb_host",
            "label_prsa_eb", "product_type"]
DOYLE_COLS = ["tic_id", "doyle_gaia_dr3", "doyle_ruwe", "doyle_parallax_over_error", "doyle_nss"]


def load_doyle_for(path: Path, tics: set[int]) -> pd.DataFrame:
    """Doyle+24 rows for our TICs, with Gaia ids read as text.

    The repo loader (load_doyle2024) lets pandas infer dtypes, so the nullable
    19-digit Gaia id columns come back as float64 and lose their last digits.
    Reading them as strings and converting to Int64 keeps them exact.
    """
    raw = pd.read_fwf(path, colspecs=d24._COLSPECS, names=d24._RAW_NAMES, compression="infer",
                      dtype={"TIC": "string", "GaiaDR3": "string", "GaiaDR2": "string"})
    raw = raw.rename(columns=d24._RENAME)
    raw["tic_id"] = pd.to_numeric(raw["tic_id"], errors="coerce").astype("Int64")
    raw = raw[raw["tic_id"].isin(tics)].copy()
    raw["doyle_gaia_dr3"] = raw["doyle_gaia_dr3"].str.strip().astype("Int64")
    return raw[DOYLE_COLS].drop_duplicates("tic_id")


def fetch_gaia_periods(source_ids: list[int]) -> pd.DataFrame:
    """source_id, gaia_eb_frequency, gaia_eb_period_days, gaia_eb_global_ranking, gaia_eb_model_type."""
    from astroquery.gaia import Gaia
    Gaia.ROW_LIMIT = -1
    frames = []
    for i in range(0, len(source_ids), BATCH):
        ids = ",".join(str(int(s)) for s in source_ids[i : i + BATCH])
        q = f"SELECT * FROM gaiadr3.vari_eclipsing_binary WHERE source_id IN ({ids})"
        for attempt in range(1, 4):
            try:
                frames.append(Gaia.launch_job(q).get_results().to_pandas())
                break
            except Exception as e:  # noqa: BLE001
                print(f"    Gaia batch {i // BATCH + 1}: attempt {attempt}/3 failed: {type(e).__name__}", flush=True)
                if attempt == 3:
                    raise
                time.sleep(30 * attempt)
    if not frames:
        return pd.DataFrame(columns=["source_id"])
    g = pd.concat(frames, ignore_index=True)
    g.columns = [c.lower() for c in g.columns]
    out = pd.DataFrame({"source_id": g["source_id"].astype("int64")})
    if "frequency" in g:
        out["gaia_eb_frequency"] = pd.to_numeric(g["frequency"], errors="coerce")
        out["gaia_eb_period_days"] = 1.0 / out["gaia_eb_frequency"]
    if "global_ranking" in g:
        out["gaia_eb_global_ranking"] = pd.to_numeric(g["global_ranking"], errors="coerce")
    if "model_type" in g:
        out["gaia_eb_model_type"] = g["model_type"].astype("string")
    return out.drop_duplicates("source_id")


def sha256(path: Path) -> str:
    with open(path, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def update_manifest(release: Path, changed: list[Path]) -> None:
    man = release / "manifest.tsv"
    if not man.exists():
        return
    rows = man.read_text().splitlines()
    header, body = rows[0], rows[1:]
    rel = {str(p.relative_to(release)) for p in changed}
    body = [r for r in body if r.split("\t", 1)[0] not in rel]
    for p in changed:
        body.append(f"{p.relative_to(release)}\t{p.stat().st_size}\t{sha256(p)}")
    man.write_text("\n".join([header] + sorted(body)) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Add RUWE and the Gaia DR3 EB holdout to a release.")
    ap.add_argument("--release", type=Path, required=True)
    ap.add_argument("--doyle", type=Path, default=DEFAULT_DOYLE)
    ap.add_argument("--gaia-eb", type=Path, default=DEFAULT_GAIA_EB)
    ap.add_argument("--tolerance", type=float, default=0.01)
    ap.add_argument("--no-gaia-query", action="store_true", help="skip the period query (membership only)")
    args = ap.parse_args()
    t0 = time.time()
    rel = args.release.resolve()

    tces = pd.read_parquet(rel / "tces_labeled.parquet", columns=TCE_COLS)
    tics = set(tces["tic_id"].astype("int64"))
    print(f"[tces] {len(tces):,} TCEs on {len(tics):,} TICs", flush=True)

    doyle = load_doyle_for(args.doyle, tics)
    doyle["tic_id"] = doyle["tic_id"].astype("int64")
    print(f"[doyle] {len(doyle):,} of {len(tics):,} TICs matched ({100 * len(doyle) / max(len(tics), 1):.1f}%)",
          flush=True)

    eb_ids = set(pd.read_parquet(args.gaia_eb, columns=["source_id"])["source_id"].astype("int64"))
    doyle["gaia_eb"] = doyle["doyle_gaia_dr3"].isin(eb_ids).fillna(False).astype(bool)
    matched_ids = sorted(int(s) for s in doyle.loc[doyle["gaia_eb"], "doyle_gaia_dr3"])
    print(f"[gaia] {len(eb_ids):,} Gaia DR3 EBs in catalog | {len(matched_ids):,} of our TICs are Gaia EBs",
          flush=True)

    periods = pd.DataFrame(columns=["source_id"])
    if matched_ids and not args.no_gaia_query:
        periods = fetch_gaia_periods(matched_ids)
        print(f"[gaia] periods fetched for {len(periods):,} stars", flush=True)
    doyle = doyle.merge(periods, how="left", left_on="doyle_gaia_dr3", right_on="source_id").drop(
        columns=["source_id"], errors="ignore")

    out = tces.merge(doyle, how="left", on="tic_id")
    out["has_doyle_params"] = out["doyle_ruwe"].notna()
    out["gaia_eb"] = out["gaia_eb"].fillna(False).astype(bool)
    if "gaia_eb_period_days" not in out:
        out["gaia_eb_period_days"] = float("nan")
    out["gaia_eb_ratio"] = [matched_ratio(p, g, args.tolerance, EB_LABEL_TARGETS) if e else None
                            for p, g, e in zip(out["orbital_period_days"], out["gaia_eb_period_days"], out["gaia_eb"])]
    out["gaia_eb_ratio"] = pd.to_numeric(out["gaia_eb_ratio"], errors="coerce")
    out["gaia_eb_period_match"] = out["gaia_eb_ratio"].notna()
    in_labels = out["label_prsa_eb"].fillna(False).astype(bool) | out["on_eb_host"].fillna(False).astype(bool)
    out["gaia_eb_independent"] = out["gaia_eb_period_match"] & ~in_labels

    keep = ["xml_filename", "planet_number", "tic_id", "has_doyle_params", "doyle_ruwe",
            "doyle_parallax_over_error", "doyle_nss", "doyle_gaia_dr3", "gaia_eb", "gaia_eb_period_days",
            "gaia_eb_ratio", "gaia_eb_period_match", "gaia_eb_independent"]
    keep += [c for c in ("gaia_eb_global_ranking", "gaia_eb_model_type") if c in out]
    path = rel / OUT_NAME
    path.parent.mkdir(exist_ok=True)
    out[keep].to_parquet(path, index=False)

    # stats
    n = len(out)
    cov_tce = out["has_doyle_params"].mean() * 100
    cov_tic = out.groupby("tic_id")["has_doyle_params"].first().mean() * 100
    n_gaia_tic = out.loc[out["gaia_eb"], "tic_id"].nunique()
    n_match = int(out["gaia_eb_period_match"].sum())
    n_indep = int(out["gaia_eb_independent"].sum())
    n_indep_tic = out.loc[out["gaia_eb_independent"], "tic_id"].nunique()
    xt = pd.crosstab(out["label"], out["gaia_eb_period_match"].map({True: "gaia_match", False: "no_match"}))
    ruwe_hi = int((out["doyle_ruwe"] > 1.4).sum())
    print(f"[ruwe] coverage {cov_tce:.1f}% of TCEs, {cov_tic:.1f}% of TICs | RUWE > 1.4: {ruwe_hi:,} TCEs", flush=True)
    print(f"[holdout] {n_gaia_tic:,} TICs are Gaia EBs | {n_match:,} TCEs period-matched | "
          f"{n_indep:,} TCEs on {n_indep_tic:,} TICs independent of the training labels", flush=True)
    print(xt.to_string(), flush=True)

    # README section (replaced if already present)
    readme = rel / "README.md"
    text = readme.read_text() if readme.exists() else ""
    text = re.split(re.escape(README_MARK), text)[0].rstrip() + "\n\n"
    text += f"""{README_MARK}

`{OUT_NAME}` has one row per TCE. Join it to `tces_labeled.parquet` on `xml_filename` and
`planet_number`.

RUWE (`doyle_ruwe`) and parallax over error come from Doyle+24 (Vizier J/MNRAS/529/1802), the same
source MegaMiner uses, so training sees the values the classifier will see in production. Coverage:
{cov_tce:.1f}% of TCEs and {cov_tic:.1f}% of TICs. Stars outside the Doyle+24 sample have null values
and `has_doyle_params = False`. `doyle_nss` is the Gaia DR3 non-single-star flag.

Gaia DR3 eclipsing binaries (`gaiadr3.vari_eclipsing_binary`, Mowlavi+2023) are matched through the
Doyle+24 Gaia DR3 id. `gaia_eb` marks {n_gaia_tic:,} TICs that are Gaia EBs. `gaia_eb_period_match` marks
{n_match:,} TCEs whose period matches the Gaia EB period (1/frequency) at 1:1, 2:1 or 1:2 within
{args.tolerance:.0%}. `gaia_eb_independent` marks the {n_indep:,} of those ({n_indep_tic:,} TICs) that are not
Prša EBs or on Prša EB hosts, so they test whether the model finds EBs our training labels missed.

These Gaia columns are an independent holdout for evaluation only. Do not use them as training labels
or features. For a clean test, keep every TIC with `gaia_eb = True` out of the training folds.
"""
    readme.write_text(text)
    update_manifest(rel, [path, readme])

    info_path = rel / "BUILD_INFO.json"
    if info_path.exists():
        info = json.loads(info_path.read_text())
        info["gaia_supplement"] = {
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "command": " ".join(sys.argv),
            "doyle": str(args.doyle), "gaia_eb": str(args.gaia_eb), "tolerance": args.tolerance,
            "ruwe_coverage_tce_pct": round(cov_tce, 2), "ruwe_coverage_tic_pct": round(cov_tic, 2),
            "gaia_eb_tics": n_gaia_tic, "gaia_eb_period_match_tces": n_match,
            "gaia_eb_independent_tces": n_indep, "periods_queried": not args.no_gaia_query,
        }
        info_path.write_text(json.dumps(info, indent=2))
        update_manifest(rel, [info_path])
    print(f"[done] {path} | {(time.time() - t0) / 60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
