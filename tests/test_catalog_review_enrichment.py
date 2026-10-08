"""Tests for CTOI/VSX TCE enrichment."""

import pandas as pd
import pytest

from tess_megastructures.annotate.catalog_review_enrichment import (
    build_catalog_review_enrichment,
    harmonic_match,
)


@pytest.mark.parametrize(("catalog_period", "ratio"), [(20.0, "1:2"), (10.0, "1:1"), (5.0, "2:1")])
def test_harmonic_match(catalog_period, ratio):
    matched, actual, error = harmonic_match(10.0, catalog_period)
    assert matched
    assert actual == ratio
    assert error == pytest.approx(0.0)


def test_enrichment_distinguishes_host_position_and_signal_matches():
    tces = pd.DataFrame(
        {"tic_id": [1, 2, 3], "planet_number": [1, 1, 1], "orbital_period_days": [10.0, 7.0, 3.0]}
    )
    ctoi = pd.DataFrame(
        {
            "TIC ID": [1, 2],
            "CTOI": ["1.01", "2.01"],
            "Period (days)": [10.05, 20.0],
            "TFOPWG Disposition": ["PC", "FP"],
        }
    )
    vsx = pd.DataFrame(
        {
            "tic_id": [2, 3],
            "Period": [7.0, 30.0],
            "Name": ["V2", "V3"],
            "Type": ["EA", "RRAB"],
            "angDist": [1.2, 2.3],
        }
    )
    out = build_catalog_review_enrichment(tces, ctoi, vsx)

    assert bool(out.loc[0, "ctoi_signal_match"])
    assert bool(out.loc[1, "ctoi_host_match"])
    assert not bool(out.loc[1, "ctoi_signal_match"])
    assert bool(out.loc[1, "vsx_signal_match"])
    assert bool(out.loc[2, "vsx_position_match"])
    assert not bool(out.loc[2, "vsx_signal_match"])
    assert out.loc[1, "vsx_min_distance_arcsec"] == pytest.approx(1.2)


def test_toi_ephemeris_and_disposition_are_retained():
    tces = pd.DataFrame({"tic_id": [10], "orbital_period_days": [4.0]})
    toi = pd.DataFrame(
        {
            "TIC ID": [10],
            "TOI": ["100.01"],
            "Period (days)": [4.0],
            "TFOPWG Disposition": ["KP"],
        }
    )
    out = build_catalog_review_enrichment(tces, pd.DataFrame(), pd.DataFrame(), toi=toi)
    assert bool(out.loc[0, "toi_signal_match"])
    assert out.loc[0, "toi_dispositions"] == "KP"


def test_requires_period_column():
    with pytest.raises(KeyError, match="orbital-period"):
        build_catalog_review_enrichment(
            pd.DataFrame({"tic_id": [1]}), pd.DataFrame(), pd.DataFrame()
        )
