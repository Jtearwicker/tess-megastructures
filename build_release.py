#!/usr/bin/env python3
"""Assemble a versioned EB-classifier training release from the DV products on disk.

Run from the repo root. Test on whatever is downloaded so far:

    uv run python build_release.py --out /mnt/buf0/jearwicker/eb_training/v1_test \
        --no-checksums --overwrite

Real release (after the pulls you want included have finished):

    uv run python build_release.py --out /mnt/buf0/jearwicker/eb_training/v1 \
        --single-sectors 1,2,3

What it does:
  1. Scans the flat DV directory, groups dvr.xml + dvt.fits by target, and keeps
     single-sector products (span start == end) and the chosen multi-sector
     span(s). Other spans (e.g. s0001-s0002) are counted and excluded. Files
     modified in the last --min-age-min minutes are skipped as possibly still
     downloading.
  2. Parses every kept dvr.xml in parallel (repo parser, one row per TCE) and
     tags each row with its source file, span and product type.
  3. Labels every TCE (add_training_labels: Prsa EBs, confirmed planets, TOI).
  4. Writes the release directory: labeled table, hard links to the data files
     (no extra disk), catalog copies, data dictionary, README with counts,
     parse errors, BUILD_INFO.json and a manifest (sha256 unless --no-checksums).
"""
from __future__ import annotations

import argparse
import datetime as dt
import errno
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from tess_megastructures.annotate.eb_labels import add_training_labels, summarize_training_labels
from tess_megastructures.ingest.parse import parse_dv_xml

REPO = Path(__file__).resolve().parent
DATA_ROOT = Path("/mnt/buf0/jearwicker/eb_data_pull")
DEFAULT_DV_DIR = DATA_ROOT / "raw/dv_ts"
DEFAULT_CATALOGS = DATA_ROOT / "catalogs"
DEFAULT_OUT = Path("/mnt/buf0/jearwicker/eb_training/v1")
CATALOG_FILES = ("vizier_prsa2022_t0.parquet", "exoarchive_pscomppars.parquet", "exoarchive_toi.parquet")
EXPECTED_TARGETS = {"s0001-s0036": 6791}  # from the MAST obs_id query for that run

# tess2018206190142-s0001-s0036-0000000025155310-00106_dvr.xml
_NAME = re.compile(r"^(?P<stem>.+-s(?P<a>\d{4})-s(?P<b>\d{4})-(?P<tic>\d+)-\d+)_(?P<kind>dvr\.xml|dvt\.fits)$")

FRONT_COLS = [
    "tic_id", "planet_number", "product_type", "dv_span", "dv_sector_start", "dv_sector_end",
    "label", "label_reason", "orbital_period_days", "xml_filename", "dvt_filename",
]


# ---------------------------------------------------------------- helpers

def parse_sector_spec(spec: str | None) -> set[int] | None:
    if spec is None or spec.strip().lower() in ("", "all"):
        return None
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def _parse_one(path_str: str):
    path = Path(path_str)
    try:
        return path.name, parse_dv_xml(path), None
    except Exception as e:  # noqa: BLE001
        return path.name, [], {"path": path_str, "error_type": type(e).__name__, "message": str(e)[:500]}


def _sha256(path_str: str) -> tuple[str, str]:
    with open(path_str, "rb") as fh:
        return path_str, hashlib.file_digest(fh, "sha256").hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _link(src: Path, dst: Path) -> str:
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError as e:
        if e.errno in (errno.EXDEV, errno.EPERM, errno.EMLINK):
            os.symlink(src, dst)
            return "symlink"
        raise


def _load_catalogs(cat: Path):
    prsa = pd.read_parquet(cat / "vizier_prsa2022_t0.parquet", columns=["TIC", "Per"])
    prsa["ticId"] = pd.to_numeric(prsa["TIC"], errors="coerce").astype("Int64")
    prsa = prsa[prsa["ticId"].notna()].copy()
    planets = pd.read_parquet(cat / "exoarchive_pscomppars.parquet", columns=["tic_id", "pl_orbper", "pl_name"])
    toi = pd.read_parquet(cat / "exoarchive_toi.parquet", columns=["tid", "toi", "tfopwg_disp", "pl_orbper"])
    return prsa, planets, toi


def _dvt_structure(example: Path | None) -> str:
    if example is None:
        return "(no dvt.fits in this release)"
    try:
        from astropy.io import fits
        lines = [f"Example: `{example.name}`", ""]
        with fits.open(example, memmap=True) as hdul:
            for i, h in enumerate(hdul):
                cols = ", ".join(h.columns.names) if getattr(h, "columns", None) is not None else ""
                lines.append(f"- HDU {i} `{h.name}`" + (f": {cols}" if cols else ""))
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        return f"(could not read {example.name}: {type(e).__name__})"


def _md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    rows = ["| " + " | ".join([df.index.name or ""] + cols) + " |",
            "|" + "---|" * (len(cols) + 1)]
    for idx, r in df.iterrows():
        rows.append("| " + " | ".join([str(idx)] + [f"{v:,}" if isinstance(v, (int,)) or hasattr(v, "item") else str(v)
                                                     for v in r.tolist()]) + " |")
    return "\n".join(rows)


# ---------------------------------------------------------------- main steps

def scan(dv_dir: Path, multi_spans: set[str], single_sectors: set[int] | None, min_age_s: float):
    now = time.time()
    groups: dict[str, dict] = defaultdict(dict)
    skipped_recent = 0
    unrecognized = 0
    with os.scandir(dv_dir) as it:
        for e in it:
            if not e.is_file(follow_symlinks=False):
                continue
            m = _NAME.match(e.name)
            if not m:
                unrecognized += 1
                continue
            if now - e.stat().st_mtime < min_age_s:
                skipped_recent += 1
                continue
            g = groups[m["stem"]]
            g[m["kind"]] = e.name
            g["a"], g["b"], g["tic"] = int(m["a"]), int(m["b"]), int(m["tic"])

    kept, excluded_spans, no_xml = [], Counter(), 0
    for stem, g in groups.items():
        span = f"s{g['a']:04d}-s{g['b']:04d}"
        if g["a"] == g["b"]:
            ok = single_sectors is None or g["a"] in single_sectors
            ptype = "single"
        else:
            ok = span in multi_spans
            ptype = "multi"
        if not ok:
            excluded_spans[span] += 1
            continue
        if "dvr.xml" not in g:
            no_xml += 1
            continue
        kept.append({"stem": stem, "span": span, "a": g["a"], "b": g["b"], "tic": g["tic"], "ptype": ptype,
                     "xml": g["dvr.xml"], "dvt": g.get("dvt.fits")})
    return kept, excluded_spans, skipped_recent, unrecognized, no_xml


def main() -> int:
    ap = argparse.ArgumentParser(description="Build an EB-classifier training release.")
    ap.add_argument("--dv-dir", type=Path, default=DEFAULT_DV_DIR)
    ap.add_argument("--catalogs", type=Path, default=DEFAULT_CATALOGS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--multi-spans", default="s0001-s0036", help="comma list of multi-sector spans to include")
    ap.add_argument("--single-sectors", default="all", help="e.g. 1,2,3 or 1-36; default all on disk")
    ap.add_argument("--min-age-min", type=float, default=15.0, help="skip files modified in the last N minutes")
    ap.add_argument("--workers", type=int, default=min(16, os.cpu_count() or 4))
    ap.add_argument("--tolerance", type=float, default=0.01)
    ap.add_argument("--no-checksums", action="store_true")
    ap.add_argument("--overwrite", action="store_true", help="replace an existing release at --out")
    args = ap.parse_args()
    t0 = time.time()

    dv_dir, out = args.dv_dir.resolve(), args.out.resolve()
    if out == dv_dir or dv_dir in out.parents or out in dv_dir.parents:
        sys.exit(f"refusing: --out {out} overlaps the data directory {dv_dir}")
    if out.exists():
        if not args.overwrite:
            sys.exit(f"{out} exists; pass --overwrite to replace it")
        if not (out / "BUILD_INFO.json").exists():
            sys.exit(f"refusing to overwrite {out}: it does not look like a release (no BUILD_INFO.json)")
        shutil.rmtree(out)  # removes our links only; the originals in dv_dir are untouched
    (out / "data").mkdir(parents=True)
    (out / "catalogs").mkdir()

    multi_spans = {s.strip() for s in args.multi_spans.split(",") if s.strip()}
    single_sectors = parse_sector_spec(args.single_sectors)

    # 1. scan
    kept, excluded_spans, skipped_recent, unrecognized, no_xml = scan(
        dv_dir, multi_spans, single_sectors, args.min_age_min * 60)
    print(f"[scan] {len(kept):,} targets kept | excluded spans {dict(excluded_spans)} | "
          f"skipped as recent {skipped_recent} | unrecognized files {unrecognized} | xml missing {no_xml}",
          flush=True)
    if not kept:
        sys.exit("nothing to build")

    # 2. parse
    by_xml = {k["xml"]: k for k in kept}
    rows, errors = [], []
    parsed_at = dt.datetime.now(dt.UTC).isoformat()
    from tess_megastructures import __version__ as parser_version
    paths = [str(dv_dir / k["xml"]) for k in kept]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for n, (name, trows, err) in enumerate(ex.map(_parse_one, paths, chunksize=64), 1):
            if err:
                errors.append(err)
                by_xml[name]["failed"] = True
            k = by_xml[name]
            for r in trows:
                r.update(xml_filename=name, dvt_filename=k["dvt"], dv_span=k["span"],
                         dv_sector_start=k["a"], dv_sector_end=k["b"], product_type=k["ptype"],
                         filename_tic=k["tic"], parser_version=parser_version, parsed_at=parsed_at)
            rows.extend(trows)
            if n % 2000 == 0:
                print(f"[parse] {n:,}/{len(paths):,} files", flush=True)
    df = pd.DataFrame(rows)
    tic_mismatch = int((pd.to_numeric(df["tic_id"], errors="coerce") != df["filename_tic"]).sum())
    df = df.drop(columns=["filename_tic"])
    print(f"[parse] {len(df):,} TCEs from {len(paths) - len(errors):,} files | {len(errors)} file errors | "
          f"TIC filename mismatches {tic_mismatch}", flush=True)

    # 3. labels
    prsa, planets, toi = _load_catalogs(args.catalogs)
    df = add_training_labels(df, prsa=prsa, planets=planets, toi=toi, tolerance=args.tolerance)
    df = df[[c for c in FRONT_COLS if c in df.columns] + [c for c in df.columns if c not in FRONT_COLS]]
    summary = summarize_training_labels(df)
    print(f"[labels] {summary['labels']}", flush=True)

    # 4. write
    df.to_parquet(out / "tces_labeled.parquet", index=False)
    link_modes = Counter()
    ok_targets = [k for k in kept if not k.get("failed")]
    for k in ok_targets:
        for fname in (k["xml"], k["dvt"]):
            if fname:
                link_modes[_link(dv_dir / fname, out / "data" / fname)] += 1
    for name in CATALOG_FILES:
        shutil.copy2(args.catalogs / name, out / "catalogs" / name)
    dd = REPO / "docs/data_dictionary.md"
    if dd.exists():
        shutil.copy2(dd, out / "data_dictionary.md")
    with open(out / "parse_errors.jsonl", "w") as fh:
        for e in errors:
            fh.write(json.dumps(e) + "\n")
    print(f"[write] table + {sum(link_modes.values()):,} data files linked {dict(link_modes)}", flush=True)

    # counts for README / BUILD_INFO
    targets = pd.DataFrame(ok_targets)
    tgt_counts = targets.groupby("span").size().rename("targets")
    tce_counts = df.groupby("dv_span").size().rename("tces")
    span_tbl = pd.concat([tgt_counts, tce_counts], axis=1).fillna(0).astype(int)
    span_tbl.index.name = "span"
    label_tbl = pd.crosstab(df["label"], df["product_type"], margins=True, margins_name="total")
    label_tbl.index.name = "label"
    reason_tbl = df["label_reason"].value_counts().rename("tces").to_frame()
    reason_tbl.index.name = "label_reason"
    n_dvt_missing = int(targets["dvt"].isna().sum())
    example = next((out / "data" / k["dvt"] for k in ok_targets if k["dvt"]), None)

    commit = _git("rev-parse", "HEAD")
    dirty = _git("status", "--porcelain")
    info = {
        "release": out.name, "built_at": dt.datetime.now(dt.UTC).isoformat(),
        "command": " ".join(sys.argv), "repo_commit": commit, "repo_dirty": bool(dirty),
        "repo_dirty_files": dirty.splitlines(), "python": platform.python_version(),
        "parser_version": parser_version, "tolerance": args.tolerance,
        "multi_spans": sorted(multi_spans),
        "single_sectors": "all on disk" if single_sectors is None else sorted(single_sectors),
        "targets": len(ok_targets), "tces": len(df), "tics": int(df["tic_id"].nunique()),
        "file_errors": len(errors), "excluded_spans": dict(excluded_spans),
        "skipped_recent_files": skipped_recent, "dvt_missing": n_dvt_missing,
        "tic_filename_mismatches": tic_mismatch, "link_modes": dict(link_modes),
        "labels": summary["labels"], "edge_cases": summary["edge_cases"],
    }
    (out / "BUILD_INFO.json").write_text(json.dumps(info, indent=2))
    write_readme(out, info, span_tbl, label_tbl, reason_tbl, summary, _dvt_structure(example))

    # 5. manifest
    files = sorted(p for p in out.rglob("*") if p.is_file() or p.is_symlink())
    sums: dict[str, str] = {}
    if not args.no_checksums:
        print(f"[manifest] sha256 of {len(files):,} files ...", flush=True)
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            sums = dict(ex.map(_sha256, [str(p) for p in files], chunksize=32))
    with open(out / "manifest.tsv", "w") as fh:
        fh.write("path\tbytes\tsha256\n")
        for p in files:
            fh.write(f"{p.relative_to(out)}\t{p.stat().st_size}\t{sums.get(str(p), '-')}\n")
    total = sum(p.stat().st_size for p in files)
    print(f"[done] {out} | {len(files):,} files, {total / 1e9:,.1f} GB | {(time.time() - t0) / 60:.1f} min",
          flush=True)
    return 0


# ---------------------------------------------------------------- README

def write_readme(out: Path, info: dict, span_tbl, label_tbl, reason_tbl, summary: dict, dvt_text: str) -> None:
    exp_lines = []
    for span, n_exp in EXPECTED_TARGETS.items():
        if span in span_tbl.index:
            n = int(span_tbl.loc[span, "targets"])
            exp_lines.append(f"- {span}: {n:,} of {n_exp:,} targets in the MAST run"
                             + ("" if n >= n_exp else " (INCOMPLETE)"))
    excluded = ", ".join(f"{k} ({v:,} targets)" for k, v in sorted(info["excluded_spans"].items())) or "none"
    ec = summary["edge_cases"]
    text = f"""# EB classifier training data, release {info['release']}

Built {info['built_at'][:19]} UTC from tess-megastructures commit `{info['repo_commit'][:12] or 'unknown'}`
{'(working tree had uncommitted changes, see BUILD_INFO.json)' if info['repo_dirty'] else ''}.

## Contents

- `tces_labeled.parquet`: one row per TCE. DV metrics parsed from dvr.xml (see `data_dictionary.md`),
  provenance columns (`xml_filename`, `dvt_filename`, `dv_span`, `product_type`) and label columns.
- `data/`: the SPOC 2-minute DV files for every target in the table (`*_dvr.xml` diagnostics and
  `*_dvt.fits` light curves). Join on `xml_filename` or `dvt_filename`.
- `catalogs/`: the label catalogs used (Prsa+2022 EBs, Exoplanet Archive pscomppars and TOI).
- `data_dictionary.md`: column definitions for the parsed DV metrics.
- `parse_errors.jsonl`: files that failed to parse ({info['file_errors']} this release).
- `BUILD_INFO.json`: build command, repo commit, counts.
- `manifest.tsv`: every file with size and sha256. Verify a copy with
  `tail -n +2 manifest.tsv | awk -F'\\t' '$3!="-"{{print $3"  "$1}}' | sha256sum -c --quiet`.

## Scope

SPOC 2-minute cadence Data Validation products only (no FFI). Two product types:

- `multi`: multi-sector DV run(s) {', '.join(info['multi_spans'])}. MegaMiner runs on these.
- `single`: single-sector DV runs, sectors: {info['single_sectors']}.

{chr(10).join(exp_lines)}

Excluded spans: {excluded}.

{_md_table(span_tbl)}

Totals: {info['targets']:,} targets, {info['tces']:,} TCEs, {info['tics']:,} unique TICs.
Targets without a dvt.fits: {info['dvt_missing']}.

## Labels

{_md_table(label_tbl)}

Rule that assigned each label (`label_reason`):

{_md_table(reason_tbl)}

A TCE matches a catalog object when the TIC agrees and the period ratio is within
{info['tolerance']:.0%} of an allowed ratio. Rules, in order of precedence:

1. Prsa EB and confirmed planet at the same period: `quarantine` (`eb_planet_conflict`).
2. Prsa EB, TCE period at 1:1, 2:1 or 1:2 of the catalog period: `eb`. The 2:1 and 1:2
   ratios are needed because SPOC often detects an EB at half or twice its period.
3. TCE on a Prsa EB host that does not match the EB period: `quarantine` (`eb_host_unmatched`).
   This outranks a planet match.
4. Confirmed planet (pscomppars, or TOI with disposition CP or KP) at 1:1 or 2:1: `planet`.
5. Planet at 1:2 (TCE at half the planet period): `quarantine` (`planet_half_period`).
6. TOI with disposition FP at 1:1, 2:1 or 1:2: `fp`.
7. Everything else: `unlabeled`.

## Caveats for training

- `unlabeled` does not mean "not an EB". Prsa+2022 covers 2-minute targets in S1-S26 only, so an EB
  first observed later has no catalog label. Treat the unlabeled pool as unknown.
- `fp` is a TOI false positive: not a planet, but a mix of EBs, blends and systematics.
  {ec['toi_fp_also_catalog_eb']:,} TOI FPs are also Prsa EBs at the same period and are labeled `eb`.
- {ec['eb_and_planet_conflict']:,} TCEs are `eb_planet_conflict`. In the S1-S2 test these were 12 known hot
  Jupiters (e.g. WASP-18 b, WASP-62 b, WASP-96 b) listed as EBs in Prsa. They are kept in quarantine
  pending a decision; relabel with
  `df.loc[df.label_reason == "eb_planet_conflict", "label"] = "planet"` if that is agreed.
- The same star appears many times: once per single-sector run it was observed in, and again in the
  multi-sector run. Split train/validation/test by `tic_id`, never by row, and consider weighting
  per TIC so continuous-viewing-zone stars (about 20 single-sector copies in S1-S36) do not dominate.
- Evaluate on `product_type == "multi"`, since that is what MegaMiner sees.
- Kostov+2025 EBs are not used in this release. Gaia DR3 EBs and RUWE are not joined yet.
- No folded or binned views are included. Build them from the dvt.fits light curves
  (`orbital_period_days`, `transit_epoch_btjd` and `weak_secondary_max_mes_phase_days` in the table
  give the fold and secondary-eclipse phase).

## dvt.fits layout

{dvt_text}

## Loading

```python
import pandas as pd
from astropy.io import fits

df = pd.read_parquet("tces_labeled.parquet")
train = df[df.label.isin(["eb", "planet", "fp"])]
row = train.iloc[0]
with fits.open(f"data/{{row.dvt_filename}}") as hdul:
    hdul.info()
```
"""
    (out / "README.md").write_text(text)


if __name__ == "__main__":
    raise SystemExit(main())
