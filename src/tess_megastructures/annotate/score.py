"""B6: Anomaly score for vetting prioritization.

The score is a numeric ranking, not a classifier. It exists to order
the candidates that pass the filter chain so vetting attention goes
to the most promising first.

v1 score:
    score = w_chisq * log10(reduced_chisq)
          + w_odd_even * log10(odd_even_sig / odd_even_threshold)
          + w_snr * log10(model_fit_snr)

Weights and reference values come from ``score_config_v1.yaml``.

The score is computed for ALL TCEs (not just survivors), so we can
later inspect the score distribution of rejected TCEs to validate
that the filter chain isn't excluding obvious high-score signals.

v2 may replace this with a learned/unsupervised approach. The function
signature should remain stable so swapping implementations is local.
"""

from __future__ import annotations

import pandas as pd


def compute_anomaly_score(tces: pd.DataFrame, score_config: dict) -> pd.DataFrame:
    """Add ``anomaly_score`` column to the TCE table.

    Parameters
    ----------
    tces : DataFrame
        Annotated TCE table.
    score_config : dict
        Parsed ``score_config_v1.yaml``.

    Returns
    -------
    DataFrame
        Copy of ``tces`` with ``anomaly_score`` (and any score components,
        named ``score_<component>``) appended.
    """
    raise NotImplementedError
