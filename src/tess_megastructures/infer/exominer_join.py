"""Join ExoMiner predictions onto the TCE sample (loose coupling, Option A).

The pipeline produces ``tce_sample_v1.parquet``; its unflagged survivors are
scored by ExoMiner (run separately, on the GPU). This module handles the two
table-level steps around that run:

1. ``write_exominer_tic_list`` -- produce the ExoMiner input: a CSV of
   ``(tic_id, sector_run)`` for the survivors to be scored.
2. ``merge_predictions`` -- join ExoMiner's prediction CSV back onto the
   sample, keyed ``(tic_id, planet_number) <-> (target_id, tce_plnt_num)``,
   scoped per sector run, validated one-to-one.
3. ``add_median_z_score`` -- compute the median of ``z_shape_0..N`` per row
   (the per-Vishal scoring; the raw ``score`` / mean is not used directly).

Conventions mirror Vishal's MegaMiner merge (merge_stratified_batch1_predictions.py):
same join keys, the same one-to-one validation, the same missing-prediction
counting. Differences: this reads the pipeline's snake_case parquet (tic_id,
planet_number, sector) rather than camelCase batch CSVs, scopes the join per
sector run so it is correct for multi-sector samples, and computes the median
z-score (which Vishal's merge did not).

ExoMiner prediction CSV schema (from the validation run):
    uid (e.g. "9155187-1-S47"), target_id, tce_plnt_num, tce_period, ...,
    z_shape_0 .. z_shape_5, EB_score, score, label_id

The TCE uid encodes the sector run as the trailing "S<sector>" token
(single-sector runs collapse to one sector, e.g. S47; multi-sector runs would
be "S36-S69"). We parse the run from the uid to scope joins robustly.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Sample (parquet) join keys -- snake_case, integer.
SAMPLE_TIC_COL = "tic_id"
SAMPLE_PLANET_COL = "planet_number"
SAMPLE_SECTOR_COL = "sector"

# Prediction (ExoMiner) join keys.
PRED_TIC_COL = "target_id"
PRED_PLANET_COL = "tce_plnt_num"
PRED_UID_COL = "uid"
PRED_SCORE_COL = "score"

# Per-Vishal: use the MEDIAN of the z_shape_* model params, not raw score / mean.
Z_SHAPE_PREFIX = "z_shape_"
MEDIAN_Z_COL = "median_z_score"


def _sector_run_str(sector: int) -> str:
    """Single-sector run token in ExoMiner's tic-list input format: 55 -> '55-55'.

    ExoMiner's run_pipeline.py expects the sector_run column as bare
    '<start>-<end>' integers (e.g. '58-58'), NOT a 'S####' MAST-query form.
    Multi-sector runs would use '<start>-<end>' with start != end. This
    pipeline currently emits single-sector samples, so start == end.
    """
    s = int(sector)
    return f"{s}-{s}"


def write_exominer_tic_list(
    survivors: pd.DataFrame,
    out_path,
    sector_col: str = SAMPLE_SECTOR_COL,
) -> pd.DataFrame:
    """Write the ExoMiner input CSV: one (tic_id, sector_run) per survivor TIC.

    ExoMiner's run_pipeline.py expects a tic list with ``tic_id`` and
    ``sector_run``. We de-duplicate to unique (tic_id, sector_run): ExoMiner
    scores per target, so one row per target/run is enough.

    Returns the written DataFrame (for inspection/testing).
    """
    if SAMPLE_TIC_COL not in survivors.columns:
        raise KeyError(f"survivors missing {SAMPLE_TIC_COL!r}")
    if sector_col not in survivors.columns:
        raise KeyError(f"survivors missing {sector_col!r}")

    df = survivors[[SAMPLE_TIC_COL, sector_col]].copy()
    df["sector_run"] = df[sector_col].map(_sector_run_str)
    out = (
        df[[SAMPLE_TIC_COL, "sector_run"]]
        .rename(columns={SAMPLE_TIC_COL: "tic_id"})
        .drop_duplicates()
        .reset_index(drop=True)
    )
    if out_path is not None:
        out.to_csv(out_path, index=False)
        logger.info("Wrote %d (tic_id, sector_run) rows -> %s", len(out), out_path)
    return out


def _read_predictions(path) -> pd.DataFrame:
    """Load an ExoMiner predictions CSV, tolerating leading '#' comment lines."""
    return pd.read_csv(path, comment="#")


def _sector_from_uid(uid: str) -> str | None:
    """Extract the sector-run token from a TCE uid like '9155187-1-S47'.

    Returns the run token ('S47' or 'S36-S69'), or None if not parseable.
    """
    if not isinstance(uid, str):
        return None
    parts = uid.split("-")
    # uid = target-tce-S<sector>  OR  target-tce-S<start>-S<end>
    run = [p for p in parts[2:] if p.startswith("S")]
    if not run:
        return None
    return "-".join(run)


def add_median_z_score(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``median_z_score`` = row-wise median of the z_shape_* columns.

    Per Vishal: the model's z_shape parameters summarized by their MEDIAN are
    the score to use, rather than the raw ``score`` (a mean-like aggregate).
    No-op (column of NaN) if no z_shape columns are present.
    """
    out = df.copy()
    z_cols = sorted(c for c in out.columns if c.startswith(Z_SHAPE_PREFIX))
    if not z_cols:
        logger.warning("no %s* columns; %s set to NaN", Z_SHAPE_PREFIX, MEDIAN_Z_COL)
        out[MEDIAN_Z_COL] = np.nan
        return out
    out[MEDIAN_Z_COL] = out[z_cols].median(axis=1, skipna=True)
    return out


def merge_predictions(
    sample: pd.DataFrame,
    predictions: pd.DataFrame,
    *,
    scope_by_sector_run: bool = True,
    rchisq_col: str | None = "model_chi_square_reduced",
) -> pd.DataFrame:
    """Left-join ExoMiner predictions onto the sample.

    Join key: (tic_id, planet_number) <-> (target_id, tce_plnt_num). When
    ``scope_by_sector_run`` is True (default), the join is additionally scoped
    by sector run -- the sample's per-row ``sector`` mapped to a run token, and
    the prediction's run parsed from its uid -- so a TIC observed in multiple
    runs is matched within the correct run (multi-sector correctness).

    All sample rows are kept (how='left'); rows ExoMiner did not score get NaN
    prediction columns. The join is validated to be at most one-to-one per
    sample row; a many-to-one match raises (signals an ambiguous TCE mapping).

    Returns the sample with prediction columns + median_z_score added.
    """
    for c in (SAMPLE_TIC_COL, SAMPLE_PLANET_COL):
        if c not in sample.columns:
            raise KeyError(f"sample missing {c!r}")
    for c in (PRED_TIC_COL, PRED_PLANET_COL):
        if c not in predictions.columns:
            raise KeyError(f"predictions missing {c!r}")

    left = sample.copy()
    right = predictions.copy()
    left[SAMPLE_TIC_COL] = left[SAMPLE_TIC_COL].astype("int64")
    left[SAMPLE_PLANET_COL] = left[SAMPLE_PLANET_COL].astype("int64")
    right[PRED_TIC_COL] = right[PRED_TIC_COL].astype("int64")
    right[PRED_PLANET_COL] = right[PRED_PLANET_COL].astype("int64")

    left_keys = [SAMPLE_TIC_COL, SAMPLE_PLANET_COL]
    right_keys = [PRED_TIC_COL, PRED_PLANET_COL]

    if scope_by_sector_run:
        if SAMPLE_SECTOR_COL not in left.columns:
            raise KeyError(f"sample missing {SAMPLE_SECTOR_COL!r} (needed to scope by run)")
        if PRED_UID_COL not in right.columns:
            raise KeyError(f"predictions missing {PRED_UID_COL!r} (needed to scope by run)")
        left["_run"] = left[SAMPLE_SECTOR_COL].map(_sector_run_str)
        right["_run"] = right[PRED_UID_COL].map(_sector_from_uid).map(_normalize_run)
        left_keys = left_keys + ["_run"]
        right_keys = right_keys + ["_run"]

    merged = left.merge(
        right,
        left_on=left_keys,
        right_on=right_keys,
        how="left",
        validate="one_to_one",
        suffixes=("", "_pred"),
    )

    # drop redundant prediction-side ID/key duplicates
    drop = [c for c in (PRED_TIC_COL, PRED_PLANET_COL) if c in merged.columns]
    drop += [c for c in merged.columns if c.endswith("_pred")]
    if "_run" in merged.columns:
        drop.append("_run")
    merged = merged.drop(columns=[c for c in dict.fromkeys(drop) if c in merged.columns])

    merged = add_median_z_score(merged)

    # report coverage
    n_total = len(merged)
    n_scored = int(merged[PRED_SCORE_COL].notna().sum()) if PRED_SCORE_COL in merged else 0
    logger.info(
        "ExoMiner join: %d/%d sample rows scored (%d unscored)",
        n_scored,
        n_total,
        n_total - n_scored,
    )

    # optional mis-join guard: warn if a matched row's rchisq disagrees wildly
    # with what the prediction implies (planetNumber/tce_plnt_num ambiguity).
    if rchisq_col and rchisq_col in merged.columns and "tce_period" in merged.columns:
        # purely advisory; we don't have a prediction rchisq, but a matched row
        # with a NaN period where a score exists is suspicious.
        suspect = merged[PRED_SCORE_COL].notna() & merged["tce_period"].isna()
        n_suspect = int(suspect.sum())
        if n_suspect:
            logger.warning(
                "%d scored rows have no matched tce_period; possible mis-join", n_suspect
            )

    return merged


def _normalize_run(run: str | None) -> str | None:
    """Normalize a uid run token to the bare '<start>-<end>' form the sample uses.

    Prediction uids carry an 'S'-prefixed run ('S47', 'S36-S69'); the sample
    side (via _sector_run_str) uses bare integers ('47-47', '36-69'). Normalize
    both to the bare form so the scoped join keys match.
    'S47' -> '47-47'; 'S36-S69' -> '36-69'; None stays None.
    """
    if run is None:
        return None
    toks = run.split("-")
    nums = []
    for t in toks:
        t = t[1:] if t.startswith("S") else t
        if not t.isdigit():
            return None
        nums.append(int(t))
    if len(nums) == 1:
        return f"{nums[0]}-{nums[0]}"
    return f"{nums[0]}-{nums[-1]}"
