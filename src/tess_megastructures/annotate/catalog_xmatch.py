"""B3: Cross-match TCEs against literature catalogs.

For each catalog enabled in ``configs/catalogs.yaml``, adds a boolean
column to the TCE table indicating whether the TIC is in that catalog:

- ``in_prsa2022_eb``
- ``in_kostov2025_eb_new``
- ``in_kostov2025_eb_known``
- ``in_doyle_high_ruwe``
- ``in_capistrant_dipper``
- ``in_tajiri_dipper``
- ``in_bouma_cpv``
- ``is_known_toi``
- ``is_confirmed_planet``

Catalogs are loaded via the corresponding modules in
:mod:`tess_megastructures.catalogs`.
"""

from __future__ import annotations

import pandas as pd


def crossmatch_all(tces: pd.DataFrame, catalog_config: dict) -> pd.DataFrame:
    """Add all catalog cross-match columns to the TCE table.

    Parameters
    ----------
    tces : DataFrame
        TCE table (post derived-metrics).
    catalog_config : dict
        Parsed contents of ``configs/catalogs.yaml``.

    Returns
    -------
    DataFrame
        Copy of ``tces`` with cross-match columns appended.
    """
    raise NotImplementedError
