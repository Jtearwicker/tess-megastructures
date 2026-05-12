"""nasa_archive catalog loader.

See ``configs/catalogs.yaml`` for source, version, and reference info.
To be implemented during the parser-refactor stage.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load(path: Path) -> pd.DataFrame:
    """Load the nasa_archive catalog from disk into a tidy DataFrame.

    Returns
    -------
    DataFrame
        Must include a ``ticId`` column (int) for cross-matching.
    """
    raise NotImplementedError
