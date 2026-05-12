"""B5: Boolean filter columns.

For every filter in the v1 chain, adds a boolean column
``failed_<filter_name>`` to the TCE table. Crucially, this stage
NEVER drops rows — the rejected sample is preserved for v2 detection
efficiency calculations.

Filters added:

Data quality (from filter_config.data_quality):
    failed_convergence
    failed_centroid
    failed_ghost
    failed_low_snr

False positive (from filter_config.false_positive):
    failed_suspected_eb        (SPOC's flag)
    failed_odd_even
    failed_period_harmonic

Catalog cross-match (from filter_config.catalog_filters):
    failed_known_eb            (any EB catalog OR simbad_is_eb)
    failed_known_dipper        (any dipper catalog)

SIMBAD (from filter_config.simbad_filter):
    failed_simbad_variable

Anomaly selection (from filter_config.anomaly):
    failed_well_fit            (inverted: True if reduced_chisq < threshold,
                                meaning the TCE IS well-fit by a planet
                                model and is therefore NOT an anomaly)

Aggregate column:
    passes_all_filters         = NOT (any of the above failed_*)
"""

from __future__ import annotations

import pandas as pd


def apply_filters(tces: pd.DataFrame, filter_config: dict) -> pd.DataFrame:
    """Add filter flag columns to the TCE table.

    Parameters
    ----------
    tces : DataFrame
        TCE table after derived metrics, period-harmonic flagging,
        catalog cross-match, and SIMBAD cross-match.
    filter_config : dict
        Parsed ``filter_config_v1.yaml``.

    Returns
    -------
    DataFrame
        Copy of ``tces`` with filter columns and ``passes_all_filters`` appended.
    """
    raise NotImplementedError
