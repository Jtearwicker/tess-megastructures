"""B1: Compute derived metrics from raw DV fields.

Adds columns to the TCE table:

- ``model_chisq_reduced`` = modelChiSquare / modelDegreesOfFreedom
- ``odd_even_significance`` = sqrt(oddEvenTransitDepthComparisonStatistic)
- ``ghost_ratio`` = coreApertureCorrelationStatistic / haloApertureCorrelationStatistic
- ``centroid_offset_significance_tic`` = TIC-position offset value/uncertainty
- ``centroid_offset_significance_control`` = control offset value/uncertainty
- ``period_to_baseline_ratio`` = orbitalPeriodDays / total_baseline_days

Division-by-zero and invalid inputs (e.g., negative argument to sqrt)
yield NaN rather than raising. NaN propagates through subsequent
filter logic.
"""

from __future__ import annotations

import pandas as pd


def add_derived_metrics(tces: pd.DataFrame, parent_sample: pd.DataFrame) -> pd.DataFrame:
    """Add derived metric columns.

    Parameters
    ----------
    tces : DataFrame
        Master TCE table.
    parent_sample : DataFrame
        Parent sample with ``total_baseline_days`` per TIC.

    Returns
    -------
    DataFrame
        Copy of ``tces`` with derived columns appended.
    """
    raise NotImplementedError
