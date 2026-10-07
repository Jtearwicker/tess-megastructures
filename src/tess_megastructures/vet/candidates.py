"""C1: Candidate selection from the annotated TCE table.

Selects TCEs that pass all filters, ranks them by anomaly score, and
writes a vetting queue.

Optionally selects a control sample of FAILED TCEs for methodological
validation: vetting these confirms that the filter chain isn't
incorrectly rejecting interesting signals.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Column produced by subsystem B (ingest/tce_sample.py):
#   in_clean_sample        -- AND of all cuts; True == survivor
#   any_diagnostic_flag    -- OR of all diagnostic flags; True == failed something
#   model_chi_square_reduced -- reduced chi-square; high == poor transit-model fit
#                               == the anomaly signal for a megastructure search
#   annotation_low_rchisq  -- boolean: flagged as low reduced-chisq (uninteresting)
SURVIVOR_COL = "in_clean_sample"
ANOMALY_SCORE_COL = "model_chi_square_reduced"


def select_candidates(
    annotated_tces: pd.DataFrame,
    output_path: Path,
    top_n: int | None = None,
    include_control_sample: bool = False,
    control_sample_size: int = 50,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Select candidates for vetting.

    Parameters
    ----------
    annotated_tces : DataFrame
        Output of subsystem B (``tces_annotated_v1.parquet``). Must contain
        the ``in_clean_sample`` gate column and, for ranking, the
        ``model_chi_square_reduced`` anomaly score.
    output_path : Path
        Where to write ``vetting_queue.parquet``.
    top_n : int, optional
        If given, take the top-N survivors by anomaly score
        (highest reduced chi-square first). Otherwise take all survivors.
    include_control_sample : bool
        If True, also include a random sample of FAILED TCEs flagged as
        ``is_control_sample = True``. Vetting these validates the filter chain.
    control_sample_size : int
        Number of control TCEs to include.
    random_seed : int
        For reproducible control sampling.

    Returns
    -------
    DataFrame
        The vetting queue (also written to ``output_path``).
    """
    if SURVIVOR_COL not in annotated_tces.columns:
        raise KeyError(
            f"annotated table missing gate column {SURVIVOR_COL!r}; "
            "run build_tce_sample first"
        )

    survivors = annotated_tces[annotated_tces[SURVIVOR_COL]].copy()

    # Rank by anomaly score (poor model fit = interesting), highest first.
    if ANOMALY_SCORE_COL in survivors.columns:
        survivors = survivors.sort_values(
            ANOMALY_SCORE_COL, ascending=False, na_position="last"
        )

    if top_n is not None:
        survivors = survivors.head(top_n)

    survivors["is_control_sample"] = False

    parts = [survivors]
    if include_control_sample:
        failed = annotated_tces[~annotated_tces[SURVIVOR_COL]]
        n = min(control_sample_size, len(failed))
        if n > 0:
            control = failed.sample(n=n, random_state=random_seed).copy()
            control["is_control_sample"] = True
            parts.append(control)

    queue = pd.concat(parts, ignore_index=True)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    queue.to_parquet(output_path, index=False)
    return queue
