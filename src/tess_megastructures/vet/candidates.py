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
        Output of subsystem B (``tces_annotated_v1.parquet``).
    output_path : Path
        Where to write ``vetting_queue.parquet``.
    top_n : int, optional
        If given, take the top-N by anomaly score. Otherwise take all
        TCEs with ``passes_all_filters``.
    include_control_sample : bool
        If True, also include a random sample of FAILED TCEs flagged
        as ``is_control_sample = True``.
    control_sample_size : int
        Number of control TCEs to include.
    random_seed : int
        For reproducible control sampling.

    Returns
    -------
    DataFrame
        The vetting queue (also written to ``output_path``).
    """
    raise NotImplementedError
