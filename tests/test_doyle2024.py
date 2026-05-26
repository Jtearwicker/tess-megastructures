"""Tests for tess_megastructures.catalogs.doyle2024.

Runs against the committed 200-row fixture
(``tests/fixtures/doyle2024_sample.dat``), plus a small synthetic
fixed-width file to exercise null handling on columns the sample uses.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tess_megastructures.catalogs.doyle2024 import load_doyle2024

FIXTURE = Path(__file__).parent / "fixtures" / "doyle2024_sample.dat"


@pytest.fixture
def doyle_df():
    return load_doyle2024(FIXTURE)


class TestLoadFixture:
    def test_loads_all_rows(self, doyle_df):
        assert len(doyle_df) == 200

    def test_has_21_columns(self, doyle_df):
        assert doyle_df.shape[1] == 21

    def test_tic_id_is_int(self, doyle_df):
        assert doyle_df["tic_id"].dtype == "int64"
        # Known first TIC from the sample
        assert doyle_df["tic_id"].iloc[0] == 248306999

    def test_doyle_prefix_on_all_but_key(self, doyle_df):
        non_key = [c for c in doyle_df.columns if c != "tic_id"]
        assert all(c.startswith("doyle_") for c in non_key)

    def test_key_columns_present(self, doyle_df):
        for col in [
            "doyle_ruwe",
            "doyle_parallax",
            "doyle_parallax_over_error",
            "doyle_teff",
            "doyle_logg",
            "doyle_radius",
            "doyle_nss",
        ]:
            assert col in doyle_df.columns

    def test_rplx_is_parallax_over_error(self, doyle_df):
        # From the first sample row: Rplx = 160.63373
        assert doyle_df["doyle_parallax_over_error"].iloc[0] == pytest.approx(160.63373, rel=1e-5)

    def test_ruwe_values_reasonable(self, doyle_df):
        # RUWE is a goodness-of-fit ratio, order unity; sanity-check range
        ruwe = doyle_df["doyle_ruwe"].dropna()
        assert (ruwe > 0).all()
        assert ruwe.median() < 5  # vast majority near 1

    def test_min_noise_has_nulls(self, doyle_df):
        # The 200-row sample has 70 blank minNoise values -> NaN
        assert doyle_df["doyle_min_noise"].isna().sum() == 70

    def test_numeric_columns_are_float(self, doyle_df):
        for col in ["doyle_parallax", "doyle_ruwe", "doyle_teff", "doyle_radius"]:
            assert doyle_df[col].dtype == "float64"


class TestNullHandling:
    """Explicitly exercise a blank in a column the sample uses (Teff),
    which the real 200-row fixture happens not to contain."""

    def test_blank_teff_becomes_nan(self, tmp_path):
        # Build a 2-row synthetic fixed-width file (396 chars/line) where
        # the second row has a blank Teff field (bytes 255-273).
        real = (
            " 248306999 6914827394429142016 6914827394429142016     "
            "312.2313788280982    -3.9523454963451576  1    "
            "2.3212265644543715 0.014450431000000001    160.63373   "
            "          12.772974000000001              0.81969833     "
            "-69.54363000000001  1.2036241            5728.141           "
            "4.3473              0.93167156         0      "
            "4.601561674532934  1.112"
        ).ljust(396)
        # Blank out Teff (bytes 255-273, i.e. indices 254:273) in a copy
        blanked = real[:254] + (" " * (273 - 254)) + real[273:]
        blanked = blanked.ljust(396)

        f = tmp_path / "synthetic.dat"
        f.write_text(real + "\n" + blanked + "\n")

        df = load_doyle2024(f)
        assert len(df) == 2
        assert not pd.isna(df["doyle_teff"].iloc[0])  # first row has Teff
        assert pd.isna(df["doyle_teff"].iloc[1])  # second row Teff blanked


class TestErrors:
    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_doyle2024("/nonexistent/path/doyle.dat")


class TestEnrichmentCompatibility:
    """The loader output must slot into the TCE sample's enrich_with_doyle:
    a tic_id column plus doyle_-prefixed params."""

    def test_mergeable_on_tic_id(self, doyle_df):
        # Simulate a tiny TCE table referencing a TIC in the sample
        tces = pd.DataFrame({"tic_id": [doyle_df["tic_id"].iloc[0], 999999999]})
        merged = tces.merge(doyle_df, on="tic_id", how="left")
        assert len(merged) == 2
        # Matched row has RUWE; unmatched is NaN
        assert not pd.isna(merged["doyle_ruwe"].iloc[0])
        assert pd.isna(merged["doyle_ruwe"].iloc[1])
