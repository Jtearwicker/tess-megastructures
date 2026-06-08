"""Catalog cross-match: flag known eclipsing binaries, annotate candidates.

Cross-matches the TCE sample against published EB catalogs by TIC and adds
boolean columns. Two distinct roles, per the agreed catalog strategy
(Vishal + Isabel, 2026-06):

- VETTED catalogs (Prsa+2022, Kostov+2025 ten-thousand) -> ``flag_*`` columns
  that DO gate candidate selection. A TCE on a vetted-EB TIC is a known binary;
  it is flagged (and thus excluded from the unflagged-survivor set and skipped
  before the expensive ExoMiner step). These flags ARE added to
  ``DIAGNOSTIC_FLAG_COLUMNS`` so they enter ``any_diagnostic_flag``.

- UNVETTED catalog (Kostov NN candidates, ~873k) -> ``annotation_*`` column
  that does NOT gate anything. The paper reports 56-86% of these are not EBs,
  so membership is recorded as a label only -- useful for known-vs-new
  provenance, never for exclusion.

Rows are NEVER dropped. Catalogs that fail to load (missing file) degrade
gracefully: their column is added as all-False and a warning is logged, so a
partial catalog set still produces a usable sample.

Columns produced
----------------
- flag_prsa_eb                 TIC in Prsa+2022 (vetted)            [flag]
- flag_kostov_eb               TIC in Kostov+2025 ten-thousand      [flag]
- flag_oddo_eb                 TIC in Oddo+2025 M+M EBs (vetted)    [flag]
- flag_catalog_eb              OR of all vetted-EB flags            [flag]
- annotation_kostov_candidate  TIC in Kostov unvetted NN list       [annotation]

``flag_catalog_eb`` is the single column callers should add to
``DIAGNOSTIC_FLAG_COLUMNS``; the per-source flags are kept for the dashboard's
per-catalog bars.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# The vetted-EB flag that should gate survivor selection. Callers append this
# to diagnostics.DIAGNOSTIC_FLAG_COLUMNS so it enters any_diagnostic_flag.
CATALOG_EB_FLAG = "flag_catalog_eb"

# Per-source vetted flags (for the dashboard's per-catalog bars).
PER_SOURCE_VETTED_FLAGS = ["flag_prsa_eb", "flag_kostov_eb", "flag_oddo_eb"]

# Annotation columns (do NOT gate anything).
CATALOG_ANNOTATION_COLUMNS = ["annotation_kostov_candidate"]


def _tic_set(loader_result: pd.DataFrame | None) -> set[int]:
    """Extract the set of TICs from a loader result, or empty set if None."""
    if loader_result is None or loader_result.empty or "ticId" not in loader_result.columns:
        return set()
    return set(loader_result["ticId"].astype("int64").tolist())


def add_catalog_flags(
    df: pd.DataFrame,
    prsa: pd.DataFrame | None = None,
    kostov_vetted: pd.DataFrame | None = None,
    kostov_unvetted: pd.DataFrame | None = None,
    oddo: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add catalog EB flags (vetted) and annotations (unvetted) to the TCE sample.

    Parameters
    ----------
    df : DataFrame
        TCE sample; must have ``tic_id`` (int).
    prsa, kostov_vetted, kostov_unvetted, oddo : DataFrame or None
        Loader outputs (each with a ``ticId`` column). Any that is None is
        treated as empty (its column becomes all-False), with a warning.

    Returns
    -------
    DataFrame
        Input with catalog flag/annotation columns added. Rows never dropped.
    """
    out = df.copy()
    if "tic_id" not in out.columns:
        raise KeyError("catalog cross-match requires a 'tic_id' column")

    tic = out["tic_id"]

    # --- vetted per-source flags ---
    prsa_tics = _tic_set(prsa)
    kostov_tics = _tic_set(kostov_vetted)
    if not prsa_tics:
        logger.warning("Prsa+2022 catalog empty/missing; flag_prsa_eb all False")
    if not kostov_tics:
        logger.warning("Kostov+2025 vetted catalog empty/missing; flag_kostov_eb all False")

    oddo_tics = _tic_set(oddo)
    if not oddo_tics:
        logger.warning("Oddo+2025 catalog empty/missing; flag_oddo_eb all False")

    out["flag_prsa_eb"] = tic.isin(prsa_tics)
    out["flag_kostov_eb"] = tic.isin(kostov_tics)
    out["flag_oddo_eb"] = tic.isin(oddo_tics)

    # --- combined vetted flag (the one that gates) ---
    out["flag_catalog_eb"] = out["flag_prsa_eb"] | out["flag_kostov_eb"] | out["flag_oddo_eb"]

    # --- unvetted annotation (does NOT gate) ---
    unvetted_tics = _tic_set(kostov_unvetted)
    if not unvetted_tics:
        logger.warning(
            "Kostov+2025 unvetted candidates empty/missing; annotation_kostov_candidate all False"
        )
    out["annotation_kostov_candidate"] = tic.isin(unvetted_tics)

    logger.info(
        "Catalog cross-match: %d Prsa, %d Kostov-vetted, %d Oddo, %d combined-vetted "
        "flagged; %d Kostov-unvetted annotated",
        int(out["flag_prsa_eb"].sum()),
        int(out["flag_kostov_eb"].sum()),
        int(out["flag_oddo_eb"].sum()),
        int(out["flag_catalog_eb"].sum()),
        int(out["annotation_kostov_candidate"].sum()),
    )
    return out
