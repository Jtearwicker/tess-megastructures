#!/usr/bin/env python3
"""Relabel an EB training release with the v1.1 label rules, without touching its data.

Reads ``<release>/tces_labeled.parquet`` (DV metrics already parsed) and writes a
labels-only update to ``<release>/labels_v1.1/``:

- ``tces_labeled_v1.1.parquet``: every TCE row with labels recomputed under
  ``rules="v1.1"`` plus the post-passes (occultation TCEs, EB evidence, hand
  overrides). The v1 call is kept in ``label_v1`` / ``label_reason_v1``, and
  ``exominer_afp_eb`` marks TCEs in Miguel's ExoMiner AFP-EB list.
- ``products_v1.1.parquet``: one label per DV product (light curve), with the v1
  product label alongside for comparison.
- ``gaia_holdout_v1.1.parquet``: the Gaia supplement plus ``gaia_holdout_independent``,
  which drops holdout stars that are in Miguel's list.
- ``label_overrides.csv`` (copy of the overrides used) and ``CHANGES_v1.1.md``.

The rules live in ``tess_megastructures.annotate.eb_labels`` (module docstring).

    uv run python relabel_release.py                       # v1 release, default paths
    uv run python relabel_release.py --no-eb-evidence-rule  # report EB evidence, don't quarantine
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
from pathlib import Path

import pandas as pd

from build_release import DEFAULT_CATALOGS, DEFAULT_OUT, _load_catalogs
from tess_megastructures.annotate.eb_labels import (
    LABELS,
    add_eb_evidence,
    add_training_labels,
    apply_label_overrides,
    product_labels,
    quarantine_planet_secondaries,
)
from tess_megastructures.annotate.period_harmonics import matched_ratio

REPO = Path(__file__).resolve().parent
MIGUEL = "tess-spoc-2min-tces-dv_s1-s98_new-labels_7-14-2026_ebs-only.csv"
DEFAULT_OVERRIDES = REPO / "configs/label_overrides_v1.1.csv"
LABEL_COLS = ["label_prsa_eb", "label_prsa_period_days", "label_prsa_ratio", "on_eb_host", "planet_match",
              "planet_half_match", "planet_match_source", "planet_match_name", "planet_match_period_days",
              "planet_match_ratio", "toi_match", "toi_disp", "toi_match_ratio", "toi_fp_match",
              "prsa_overridden_by_planet", "label", "label_reason"]


def sha256(path: Path) -> str:
    with open(path, "rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def period_col(df: pd.DataFrame) -> str | None:
    return next((c for c in df.columns if c.lower().startswith("per")), None)


def kostov_vetted(cat: Path) -> pd.DataFrame | None:
    parts = [pd.read_parquet(p) for p in (cat / "vizier_kostov2025_t0.parquet", cat / "vizier_kostov2025_t1.parquet")
             if p.exists()]
    if not parts:
        return None
    k = pd.concat(parts, ignore_index=True)
    tcol = next((c for c in k.columns if c.upper() in ("TIC", "TICID", "TIC_ID")), None)
    if tcol is None:
        print(f"[kostov] no TIC column in {list(k.columns)[:15]}; skipped")
        return None
    k["ticId"] = pd.to_numeric(k[tcol], errors="coerce")
    return k[k.ticId.notna()]


def md_counts(s: pd.Series) -> str:
    return "\n".join(f"| {' -> '.join(map(str, k)) if isinstance(k, tuple) else k} | {v:,} |" for k, v in s.items())


def main() -> int:
    ap = argparse.ArgumentParser(description="Relabel an EB training release with the v1.1 rules.")
    ap.add_argument("--release", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--catalogs", type=Path, default=DEFAULT_CATALOGS)
    ap.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    ap.add_argument("--no-eb-evidence-rule", action="store_true",
                    help="compute eb_evidence but keep EB labels that have none")
    args = ap.parse_args()
    out_dir = args.release / "labels_v1.1"
    out_dir.mkdir(exist_ok=True)

    df = pd.read_parquet(args.release / "tces_labeled.parquet")
    df["label_v1"], df["label_reason_v1"] = df["label"], df["label_reason"]
    df = df.drop(columns=[c for c in LABEL_COLS if c in df.columns])
    print(f"[load] {len(df):,} TCEs, {df.tic_id.nunique():,} TICs, {df.dvt_filename.nunique():,} products", flush=True)

    prsa, planets, toi = _load_catalogs(args.catalogs)
    df = add_training_labels(df, prsa=prsa, planets=planets, toi=toi, rules="v1.1")
    df = quarantine_planet_secondaries(df, product_col="xml_filename")

    mig = pd.read_csv(args.catalogs / MIGUEL)
    indep = [(mig[~mig.phot_label_source.astype(str).str.contains("prsa", case=False)]
              .assign(ticId=lambda d: d.target_id), "tce_period", "exominer_kostov_sg1")]
    kos = kostov_vetted(args.catalogs)
    if kos is not None:
        indep.append((kos, period_col(kos), "kostov_vetted"))
        print(f"[kostov] {len(kos):,} vetted rows, period column {period_col(kos)!r}", flush=True)
    df = add_eb_evidence(df, independent=indep, apply=not args.no_eb_evidence_rule)

    overrides = pd.read_csv(args.overrides) if args.overrides.exists() else None
    df = apply_label_overrides(df, overrides)

    mmap = mig.groupby("target_id")["tce_period"].apply(list).to_dict()
    df["exominer_afp_eb"] = [any(matched_ratio(p, q) is not None for q in mmap.get(int(t), []))
                             for t, p in zip(df.tic_id, df.orbital_period_days)]

    # products, with the v1 product label for comparison
    prod = product_labels(df)
    v1 = product_labels(df.assign(label=df.label_v1, label_reason=df.label_reason_v1))
    prod = prod.merge(v1[["dvt_filename", "product_label", "product_label_reason"]].rename(
        columns={"product_label": "product_label_v1", "product_label_reason": "product_label_reason_v1"}),
        on="dvt_filename", how="left")

    # Gaia holdout without stars in Miguel's ExoMiner AFP-EB list
    sup_path = args.release / "supplementary/gaia_ruwe_holdout.parquet"
    hold = None
    if sup_path.exists():
        hold = pd.read_parquet(sup_path)
        add = ["xml_filename", "planet_number", "exominer_afp_eb"] + ([] if "tic_id" in hold else ["tic_id"])
        hold = hold.merge(df[add], on=["xml_filename", "planet_number"], how="left")
        if "gaia_eb_period_match" not in hold:
            hold["gaia_eb_period_match"] = False
        star = hold.groupby("tic_id").exominer_afp_eb.transform("any")
        hold["holdout_star_in_exominer"] = star.fillna(False).astype(bool)
        hold["gaia_holdout_independent"] = hold.gaia_eb_period_match.fillna(False).astype(bool) & ~hold.holdout_star_in_exominer

    # write
    paths = {"tces_labeled_v1.1.parquet": df, "products_v1.1.parquet": prod}
    if hold is not None:
        paths["gaia_holdout_v1.1.parquet"] = hold
    for name, d in paths.items():
        d.to_parquet(out_dir / name, index=False)
    if overrides is not None:
        overrides.to_csv(out_dir / "label_overrides.csv", index=False)

    # summary
    lab = df.label.value_counts().reindex(LABELS, fill_value=0)
    lab1 = df.label_v1.value_counts().reindex(LABELS, fill_value=0)
    moved = df[df.label != df.label_v1].groupby(["label_v1", "label", "label_reason"]).size().rename("tces")
    plab = prod.product_label.value_counts().reindex(LABELS, fill_value=0)
    plab1 = prod.product_label_v1.value_counts().reindex(LABELS, fill_value=0)
    pmoved = prod[prod.product_label != prod.product_label_v1].groupby(
        ["product_label_v1", "product_label", "product_label_reason"]).size().rename("products")
    ev = df.assign(e=df.eb_evidence.replace("", "none").str.split(";")).explode("e")
    ev_rate = (ev[ev.label_v1.isin(["eb", "planet"])].groupby(["label_v1", "e"]).tic_id.size()
               .unstack(0).fillna(0).astype(int))

    print("\n[TCE labels] v1 -> v1.1")
    print(pd.DataFrame({"v1": lab1, "v1.1": lab}).to_string())
    print("\n[TCE changes]")
    print(moved.sort_values(ascending=False).to_string())
    print("\n[product labels] v1 -> v1.1")
    print(pd.DataFrame({"v1": plab1, "v1.1": plab}).to_string())
    print("\n[product changes]")
    print(pmoved.sort_values(ascending=False).head(25).to_string())
    print("\n[EB evidence] TCE counts by v1 label (a TCE can have several kinds)")
    print(ev_rate.to_string())
    if hold is not None:
        st = hold.assign(pm=hold.gaia_eb_period_match.fillna(False).astype(bool)).groupby("tic_id").agg(
            pm=("pm", "any"), mig=("holdout_star_in_exominer", "any"), ind=("gaia_holdout_independent", "any"))
        print(f"\n[gaia holdout] stars with a Gaia period match {int(st.pm.sum()):,} | "
              f"of those in Miguel's list {int((st.pm & st.mig).sum()):,} | independent {int(st.ind.sum()):,}")

    with open(out_dir / "CHANGES_v1.1.md", "w") as fh:
        fh.write(f"# Labels v1.1\n\nBuilt {dt.datetime.now(dt.UTC).isoformat()} by `relabel_release.py` from "
                 f"`{args.release / 'tces_labeled.parquet'}`. The data files are unchanged.\n\n"
                 f"Rules: see the module docstring of `tess_megastructures/annotate/eb_labels.py`. "
                 f"EB evidence rule {'OFF (reported only)' if args.no_eb_evidence_rule else 'ON'}.\n\n"
                 "## TCE labels\n\n| label | v1 | v1.1 |\n|---|---:|---:|\n"
                 + "\n".join(f"| {k} | {lab1[k]:,} | {lab[k]:,} |" for k in LABELS)
                 + "\n\n## TCE changes (v1 label, v1.1 label, reason)\n\n| change | TCEs |\n|---|---:|\n"
                 + md_counts(moved.sort_values(ascending=False))
                 + "\n\n## Product labels\n\n| label | v1 | v1.1 |\n|---|---:|---:|\n"
                 + "\n".join(f"| {k} | {plab1[k]:,} | {plab[k]:,} |" for k in LABELS)
                 + "\n\n## Files\n\n| file | sha256 |\n|---|---|\n"
                 + "\n".join(f"| `{n}` | `{sha256(out_dir / n)}` |" for n in paths) + "\n")
    print(f"\n[done] wrote {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
