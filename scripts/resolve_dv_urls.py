#!/usr/bin/env python3
"""Resolve real MAST DV report URLs for dashboard survivors (offline step).

Why this exists
---------------
A SPOC 2-min DV report filename carries the pipeline processing timestamp and a
product id, so it cannot be constructed from (tic, sector, tce). Instead of
guessing filenames, we ask MAST which DV products actually exist for each target
and pick the right one per (planet_number, sector-run). This also works if a
target's DV products live in the HLSP tess-spoc collection: we key on what MAST
returns, not on an assumed collection.

Output
------
A parquet with one row per survivor, columns:
    tic_id, planet_number, sector, dv_key, dv_url, dv_report_url, dv_source, resolved
- dv_url         : per-candidate DV summary (_dvs) for this planet_number when
                   available, else the full DV report (_dvr).
- dv_report_url  : the full DV report (_dvr) for the matched run.
- dv_source      : "candidate" | "report" | "none".
- dv_key         : "{tic}-{planet_number}-{sector}", the join key the dashboard uses.

The dashboard (make_dashboard_multisector.py --dv-links) left-joins this and
renders dv_url. It does no network itself.

Run this on the node (MAST reachable). It caches the raw per-TIC product listing
to JSON, so reruns are fast and only query TICs not seen before.

Usage
-----
    python scripts/resolve_dv_urls.py signals_v1_collapsed.parquet \
        --top-n 10000 --output dv_links.parquet

Keep --top-n equal to the dashboard's --top-n so every embedded row has an entry.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

DL = "https://mast.stsci.edu/api/v0.1/Download/file?uri="

# The zero-padded TIC is the only 16-digit run in both SPOC-2min and HLSP names.
_RE_TIC = re.compile(r"(\d{16})")
_RE_RUN = re.compile(r"-s(\d{4})-s(\d{4})[-_]")
# per-candidate summary TCE index:
#   SPOC 2-min : "...-NN-<pin>_dvs.pdf"
#   HLSP       : "..._dvs-NN.pdf" / "..._dvs_NN.pdf"
_RE_TCE_SPOC = re.compile(r"-(\d{2})-\d+_dvs\.pdf$")
_RE_TCE_HLSP = re.compile(r"_dvs[-_](\d+)\.pdf$")


def _parse(filename: str):
    """Return (tic, s0, s1, kind, tce) parsed from a DV product filename.

    kind is "report" (_dvr), "summary" (_dvs), or None (anything else, e.g.
    _dvm mini-reports and _dvt time series, which we ignore).
    """
    tic = None
    m = _RE_TIC.search(filename)
    if m:
        tic = int(m.group(1))
    s0 = s1 = None
    m = _RE_RUN.search(filename)
    if m:
        s0, s1 = int(m.group(1)), int(m.group(2))
    kind = None
    tce = None
    if filename.endswith("_dvr.pdf"):
        kind = "report"
    elif filename.endswith("_dvs.pdf") or "_dvs-" in filename or "_dvs_" in filename:
        kind = "summary"
        mm = _RE_TCE_SPOC.search(filename) or _RE_TCE_HLSP.search(filename)
        if mm:
            tce = int(mm.group(1))
    elif filename.endswith("_dvm.pdf"):
        kind = "mini"
    return tic, s0, s1, kind, tce


def fetch_products(tics, cache, chunk=25, sleep=0.0, log=print):
    """Fill cache[str(tic)] with a list of DV product dicts for TICs not present.

    Queries MAST in chunks. A target with no DV products is cached as [] so it
    is not re-queried on the next run.
    """
    from astroquery.mast import Observations

    todo = [t for t in tics if str(t) not in cache]
    log(f"  {len(todo)} TICs to query, {len(tics) - len(todo)} already cached")
    for i in range(0, len(todo), chunk):
        batch = [str(t) for t in todo[i : i + chunk]]
        for t in batch:
            cache.setdefault(t, [])  # mark seen up front
        try:
            # Query across all collections: MegaMiner survivors are a mix of
            # 2-min SPOC ("tess...") and FFI tess-spoc ("hlsp_tess-spoc...") DV
            # products. Restricting to obs_collection="TESS" hid the FFI ones.
            obs = Observations.query_criteria(target_name=batch)
            if len(obs):
                prod = Observations.get_product_list(obs)
                # Read the raw product list directly (filter_products(extension="pdf")
                # was dropping _dvr/_dvs while keeping _dvm). Accept only the two DV
                # naming schemes we understand so unrelated collections can't slip in.
                for row in prod:
                    fn = str(row["productFilename"])
                    if "_dv" not in fn or not fn.endswith(".pdf"):
                        continue
                    is_hlsp = fn.startswith("hlsp_tess-spoc")
                    if not (is_hlsp or re.match(r"tess\d", fn)):
                        continue
                    tic, s0, s1, kind, tce = _parse(fn)
                    if tic is None or kind is None:
                        log(f"    unparsed DV file: {fn}")
                        continue
                    cache.setdefault(str(tic), []).append(
                        {
                            "filename": fn,
                            "uri": str(row["dataURI"]),
                            "kind": kind,
                            "tce": tce,
                            "s0": s0,
                            "s1": s1,
                            "hlsp": is_hlsp,
                        }
                    )
        except Exception as e:  # keep going; validation catches low resolve rates
            log(f"    batch {i // chunk} query failed: {e}")
        log(f"  queried {min(i + chunk, len(todo))}/{len(todo)}")
        if sleep:
            time.sleep(sleep)
    return cache


def _run_key(sector):
    """Sort key factory: prefer single-sector run == representative sector,
    then a multi-sector run containing it (widest first), then anything.
    Native 2-min SPOC products win over FFI tess-spoc on otherwise-equal ties."""

    def key(p):
        hlsp = 1 if p.get("hlsp") else 0
        s0, s1 = p.get("s0"), p.get("s1")
        if s0 is None or s1 is None:
            return (3, 0, hlsp)
        if s0 == s1 == sector:
            return (0, 0, hlsp)
        if s0 <= sector <= s1:
            return (1, -(s1 - s0), hlsp)
        return (2, -(s1 - s0), hlsp)

    return key


def pick(products, planet_number, sector):
    """Choose (dv_url, dv_report_url, source) for one survivor row."""
    reports = [p for p in products if p["kind"] == "report"]
    summaries = [p for p in products if p["kind"] == "summary"]
    minis = [p for p in products if p["kind"] == "mini"]
    key = _run_key(sector)

    cand = sorted([p for p in summaries if p.get("tce") == planet_number], key=key)
    reports_sorted = sorted(reports, key=key)
    minis_sorted = sorted(minis, key=key)

    if cand:
        rep = cand[0]
        # pair with the full report from the same run when possible
        same = [p for p in reports if p.get("s0") == rep.get("s0") and p.get("s1") == rep.get("s1")]
        report = same[0] if same else (reports_sorted[0] if reports_sorted else None)
        return DL + rep["uri"], (DL + report["uri"]) if report else None, "candidate"
    if reports_sorted:
        return DL + reports_sorted[0]["uri"], DL + reports_sorted[0]["uri"], "report"
    if minis_sorted:
        return DL + minis_sorted[0]["uri"], None, "mini"
    return None, None, "none"


def main(argv):
    ap = argparse.ArgumentParser(description="Resolve MAST DV report URLs for dashboard survivors.")
    ap.add_argument("survivors", type=Path, help="signals_v1_collapsed.parquet (dashboard input)")
    ap.add_argument("-o", "--output", type=Path, default=Path("dv_links.parquet"))
    ap.add_argument(
        "--cache",
        type=Path,
        default=Path("dv_product_cache.json"),
        help="Per-TIC MAST product listing cache (JSON), reused across runs.",
    )
    ap.add_argument(
        "--top-n",
        type=int,
        default=10000,
        help="Resolve only the top-N survivors by anomaly_score. Match the dashboard --top-n.",
    )
    ap.add_argument("--max-tics", type=int, default=0, help="Cap unique TICs (0 = all). For a quick sample.")
    ap.add_argument("--chunk", type=int, default=25, help="TICs per MAST query.")
    ap.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between chunks.")
    args = ap.parse_args(argv)

    df = pd.read_parquet(args.survivors)
    need = ["tic_id", "planet_number", "sector"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        print(f"ERROR: survivors missing columns: {missing}")
        return 1

    if args.top_n and args.top_n > 0 and "anomaly_score" in df.columns:
        df = df.sort_values("anomaly_score", ascending=False, na_position="last").head(args.top_n)

    keys = df[need].dropna(subset=["tic_id"]).copy()
    keys["tic_id"] = keys["tic_id"].astype(int)
    keys["planet_number"] = pd.to_numeric(keys["planet_number"], errors="coerce").astype("Int64")
    keys["sector"] = pd.to_numeric(keys["sector"], errors="coerce").astype("Int64")

    # Unique TICs in anomaly-ranking order (keys inherits the sorted df order),
    # so --max-tics samples the top of the ranking, not the lowest ids.
    tics = list(dict.fromkeys(keys["tic_id"].tolist()))
    if args.max_tics:
        tics = tics[: args.max_tics]
    ticset = set(tics)
    print(f"{len(keys):,} survivor rows, {len(tics):,} unique TICs to resolve")

    cache = {}
    if args.cache.is_file():
        cache = json.loads(args.cache.read_text())
        print(f"loaded cache: {len(cache):,} TICs")
    fetch_products(tics, cache, chunk=args.chunk, sleep=args.sleep)
    args.cache.write_text(json.dumps(cache))
    print(f"cache now {len(cache):,} TICs -> {args.cache}")

    out_rows = []
    n_res = 0
    for _, r in keys.iterrows():
        tic = int(r["tic_id"])
        if tic not in ticset:
            continue
        pn = None if pd.isna(r["planet_number"]) else int(r["planet_number"])
        sec = None if pd.isna(r["sector"]) else int(r["sector"])
        prods = cache.get(str(tic), [])
        dv_url, dv_report_url, src = pick(prods, pn, sec) if prods else (None, None, "none")
        if dv_url:
            n_res += 1
        dv_key = None if (pn is None or sec is None) else f"{tic}-{pn}-{sec}"
        out_rows.append(
            {
                "tic_id": tic,
                "planet_number": pn,
                "sector": sec,
                "dv_key": dv_key,
                "dv_url": dv_url,
                "dv_report_url": dv_report_url,
                "dv_source": src,
                "resolved": dv_url is not None,
            }
        )

    out = pd.DataFrame(out_rows)
    out.to_parquet(args.output, index=False)
    tot = len(out)
    print(f"resolved {n_res:,}/{tot:,} rows ({100 * n_res / max(tot, 1):.1f}%) -> {args.output}")
    print("dv_source:", out["dv_source"].value_counts().to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
