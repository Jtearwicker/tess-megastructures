"""Loader for the Doyle+24 TESS-SPOC FFI Main Sequence Target Sample.

Reads the fixed-width catalog file (Vizier J/MNRAS/529/1802, ~2.3M rows)
and returns a clean DataFrame keyed on ``tic_id`` with Gaia-derived
stellar parameters, column-renamed to the ``doyle_``-prefixed schema the
TCE sample's enrichment step expects.

Catalog reference
-----------------
Doyle L., Armstrong D.J., Bayliss D., Rodel T., Kunovac V. (2024),
MNRAS 529, 1802. "The TESS SPOC FFI target sample explored with Gaia."
Vizier: J/MNRAS/529/1802, table ``targets`` (2,319,308 rows, 21 columns).

The file is fixed-width (record length 396). Column byte positions and
meanings come from the catalog ReadMe (committed at
``tests/fixtures/doyle2024_ReadMe.txt``). Missing/optional fields are
blank-padded in the file and parsed as NaN.

The loader reads a LOCAL file (gzipped or plain). It does not query
Vizier; the catalog is downloaded once and stored durably (on the
cluster, ``/mnt/primary/TESS/catalogs/doyle2024/targets.dat.gz``).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Byte-by-byte column spec from the Vizier ReadMe (J/MNRAS/529/1802).
# ReadMe positions are 1-indexed inclusive "a- b"; pandas read_fwf wants
# 0-indexed half-open [start, end), i.e. (a-1, b).
_COLSPECS = [
    (0, 10),  # TIC        1-10    I10
    (11, 30),  # GaiaDR3    12-30   I19  (nullable)
    (31, 50),  # GaiaDR2    32-50   I19  (nullable)
    (51, 72),  # RAdeg      52-72   E21.19 deg
    (73, 95),  # DEdeg      74-95   E22.19 deg
    (96, 98),  # Nsectors   97-98   I2
    (99, 120),  # plx        100-120 E21.18 mas
    (121, 142),  # e_plx      122-142 F21.19 mas
    (143, 166),  # Rplx       144-166 F23.17  (parallax_over_error)
    (167, 186),  # Gmag       168-186 F19.16 mag  (nullable)
    (187, 209),  # BP-RP      188-209 E22.17 mag
    (210, 232),  # RV         211-232 E22.17 km/s (nullable)
    (233, 253),  # e_RV       234-253 F20.17 km/s (nullable)
    (254, 273),  # Teff       255-273 F19.13 K
    (274, 292),  # logg       275-292 F18.16 [cm/s2]
    (293, 312),  # RUWE       294-312 F19.16
    (313, 314),  # NSS        314     I1
    (315, 337),  # GMAG       316-337 E22.16 mag  (nullable)
    (338, 358),  # Rad        339-358 F20.17 Rsun (nullable)
    (359, 373),  # minNoise   360-373 E14.9 ppm   (nullable)
    (374, 396),  # TwoRadius  375-396 F22.17 Earth (nullable)
]

# Raw column names (match the ReadMe labels; BP-RP -> BP_RP for a valid identifier).
_RAW_NAMES = [
    "TIC",
    "GaiaDR3",
    "GaiaDR2",
    "RAdeg",
    "DEdeg",
    "Nsectors",
    "plx",
    "e_plx",
    "Rplx",
    "Gmag",
    "BP_RP",
    "RV",
    "e_RV",
    "Teff",
    "logg",
    "RUWE",
    "NSS",
    "GMAG",
    "Rad",
    "minNoise",
    "TwoRadius",
]

# Map raw catalog columns -> output schema. The join key becomes tic_id;
# everything else gets a doyle_ prefix so it never clobbers the DV-extracted
# stellar params the TCE sample treats as primary.
_RENAME = {
    "TIC": "tic_id",
    "GaiaDR3": "doyle_gaia_dr3",
    "GaiaDR2": "doyle_gaia_dr2",
    "RAdeg": "doyle_ra_deg",
    "DEdeg": "doyle_dec_deg",
    "Nsectors": "doyle_n_sectors",
    "plx": "doyle_parallax",
    "e_plx": "doyle_parallax_error",
    "Rplx": "doyle_parallax_over_error",
    "Gmag": "doyle_g_mag",
    "BP_RP": "doyle_bp_rp",
    "RV": "doyle_rv",
    "e_RV": "doyle_rv_error",
    "Teff": "doyle_teff",
    "logg": "doyle_logg",
    "RUWE": "doyle_ruwe",
    "NSS": "doyle_nss",
    "GMAG": "doyle_abs_g_mag",
    "Rad": "doyle_radius",
    "minNoise": "doyle_min_noise",
    "TwoRadius": "doyle_two_radius",
}


def load_doyle2024(path: str | Path) -> pd.DataFrame:
    """Load the Doyle+24 catalog into a clean, ``doyle_``-prefixed DataFrame.

    Parameters
    ----------
    path : str or Path
        Path to the catalog file. May be gzipped (``.dat.gz``) or plain
        (``.dat``); pandas infers compression from the extension.

    Returns
    -------
    pandas.DataFrame
        One row per catalog target. ``tic_id`` is int64 (the join key);
        all other columns carry a ``doyle_`` prefix. Blank/optional fields
        are NaN. Column order follows the catalog.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Doyle+24 catalog not found: {path}")

    logger.info("Loading Doyle+24 catalog from %s", path)
    df = pd.read_fwf(
        path,
        colspecs=_COLSPECS,
        names=_RAW_NAMES,
        compression="infer",
    )

    df = df.rename(columns=_RENAME)

    # tic_id is the join key and must be a clean integer. Rows without a
    # valid TIC are unusable for the cross-match; drop them (should be none
    # in practice, but guards against a malformed trailing line).
    before = len(df)
    df = df[df["tic_id"].notna()].copy()
    if len(df) < before:
        logger.warning("Dropped %d rows with missing TIC", before - len(df))
    df["tic_id"] = df["tic_id"].astype("int64")

    logger.info("Loaded %d Doyle+24 targets", len(df))
    return df
