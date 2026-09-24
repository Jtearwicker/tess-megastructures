"""Tests for tess_megastructures.annotate.eb_labels: every precedence path of
add_training_labels on small synthetic catalogs (no data files needed)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tess_megastructures.annotate.eb_labels import (
    _tic_int,
    add_period_matched_eb_labels,
    add_training_labels,
    summarize_training_labels,
)


@pytest.fixture
def catalogs():
    prsa = pd.DataFrame({
        "TIC": ["0000000100", "0000000200", "0000001000"],
        "Per": [2.0, 5.0, 1.2],
    })
    prsa["ticId"] = pd.to_numeric(prsa["TIC"]).astype("int64")
    planets = pd.DataFrame({
        "tic_id": ["TIC 300", "TIC 200", "TIC 100", "TIC 400", "TIC 1100", "TIC 1100", None],
        "pl_orbper": [3.0, 7.0, 2.0, 4.0, 3.0, 6.0, 9.0],
        "pl_name": ["P300 b", "P200 b", "P100 b", "P400 b", "P1100 b", "P1100 c", "Kepler-x b"],
    })
    toi = pd.DataFrame({
        "tid": [500, 600, 700, 800, 1000],
        "toi": [500.01, 600.01, 700.01, 800.01, 1000.01],
        "tfopwg_disp": ["FP", "PC", "CP", "KP", "FP"],
        "pl_orbper": [6.0, 1.5, 10.0, 8.0, 1.2],
    })
    return prsa, planets, toi


@pytest.fixture
def labeled(catalogs):
    prsa, planets, toi = catalogs
    tces = pd.DataFrame({
        "tic_id": [100, 200, 200, 300, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 300],
        "orbital_period_days": [2.0, 2.5, 7.0, 3.0, 6.0, 2.0, 6.0, 1.5, 10.0, 16.0, 3.3, 1.2, 3.0, np.nan],
    })
    return add_training_labels(tces, prsa=prsa, planets=planets, toi=toi)


def row(df, i):
    return df.iloc[i]


class TestTicParsing:
    @pytest.mark.parametrize("value, expected", [
        ("TIC 300", 300), ("0000000200", 200), (123, 123), (np.int64(7), 7),
        (5.0, 5), (None, None), (np.nan, None), (True, None), ("no digits", None),
    ])
    def test_tic_int(self, value, expected):
        assert _tic_int(value) == expected


class TestPrecedence:
    def test_eb_and_planet_conflict_is_quarantined(self, labeled):
        r = row(labeled, 0)  # TIC 100 at 2.0: Prsa EB and a planet at the same period
        assert r["label"] == "quarantine" and r["label_reason"] == "eb_planet_conflict"

    def test_eb_at_half_period_is_eb(self, labeled):
        r = row(labeled, 1)  # TIC 200 at 2.5 = Prsa 5.0 / 2
        assert r["label"] == "eb" and r["label_reason"] == "prsa_eb"
        assert r["label_prsa_ratio"] == 0.5

    def test_planet_on_eb_host_is_quarantined(self, labeled):
        r = row(labeled, 2)  # TIC 200 at 7.0: planet match, EB host, not EB-matched
        assert r["label"] == "quarantine" and r["label_reason"] == "eb_host_unmatched"
        assert bool(r["planet_match"]) and bool(r["on_eb_host"])

    def test_planet_one_to_one(self, labeled):
        r = row(labeled, 3)
        assert r["label"] == "planet" and r["label_reason"] == "planet_pscomppars"
        assert r["planet_match_ratio"] == 1.0 and r["planet_match_name"] == "P300 b"

    def test_planet_two_to_one(self, labeled):
        r = row(labeled, 4)  # TCE at twice the planet period
        assert r["label"] == "planet" and r["planet_match_ratio"] == 2.0

    def test_planet_half_period_is_quarantined(self, labeled):
        r = row(labeled, 5)  # TIC 400 at 2.0 = planet 4.0 / 2
        assert r["label"] == "quarantine" and r["label_reason"] == "planet_half_period"
        assert not bool(r["planet_match"]) and bool(r["planet_half_match"])

    def test_toi_fp(self, labeled):
        r = row(labeled, 6)
        assert r["label"] == "fp" and r["label_reason"] == "toi_fp" and bool(r["toi_fp_match"])

    def test_toi_pc_is_unlabeled_with_disposition(self, labeled):
        r = row(labeled, 7)
        assert r["label"] == "unlabeled" and r["toi_disp"] == "PC"

    def test_toi_cp_is_planet(self, labeled):
        r = row(labeled, 8)
        assert r["label"] == "planet" and r["label_reason"] == "planet_toi_cp"
        assert r["planet_match_name"] == "TOI-700.01"

    def test_toi_kp_two_to_one_is_planet(self, labeled):
        r = row(labeled, 9)
        assert r["label"] == "planet" and r["label_reason"] == "planet_toi_kp"

    def test_no_match_is_unlabeled(self, labeled):
        r = row(labeled, 10)
        assert r["label"] == "unlabeled" and r["label_reason"] == "none"

    def test_fp_that_is_catalog_eb_is_eb(self, labeled):
        r = row(labeled, 11)  # TOI FP and Prsa EB at the same period
        assert r["label"] == "eb" and bool(r["toi_fp_match"])

    def test_multiplanet_prefers_one_to_one(self, labeled):
        r = row(labeled, 12)  # 3.0 matches planet b at 1:1 and planet c at 1:2
        assert r["label"] == "planet" and r["planet_match_name"] == "P1100 b"

    def test_missing_period_is_unlabeled(self, labeled):
        r = row(labeled, 13)
        assert r["label"] == "unlabeled"


class TestShapeAndSummary:
    def test_rows_never_dropped(self, labeled):
        assert len(labeled) == 14

    def test_every_row_has_one_known_label(self, labeled):
        assert set(labeled["label"]) <= {"eb", "planet", "fp", "quarantine", "unlabeled"}
        assert labeled["label"].notna().all()

    def test_summary_edge_cases(self, labeled):
        s = summarize_training_labels(labeled)
        assert s["labels"] == {"eb": 2, "planet": 5, "fp": 1, "quarantine": 3, "unlabeled": 3}
        e = s["edge_cases"]
        assert e["eb_and_planet_conflict"] == 1
        assert e["planet_match_on_eb_host"] == 1
        assert e["planet_half_period_quarantined"] == 1
        assert e["toi_fp_also_catalog_eb"] == 1

    def test_missing_catalogs_degrade(self):
        tces = pd.DataFrame({"tic_id": [1, 2], "orbital_period_days": [1.0, 2.0]})
        out = add_training_labels(tces)
        assert list(out["label"]) == ["unlabeled", "unlabeled"]

    def test_extra_eb_catalog(self, catalogs):
        prsa, planets, toi = catalogs
        kostov = pd.DataFrame({"ticId": [900], "Per-TESS": [6.6]})
        tces = pd.DataFrame({"tic_id": [900, 900], "orbital_period_days": [3.3, 4.0]})
        out = add_training_labels(tces, prsa=prsa, planets=planets, toi=toi,
                                  extra_eb=[(kostov, "Per-TESS")])
        assert list(out["label"]) == ["eb", "quarantine"]
        assert list(out["label_reason"]) == ["extra_eb", "eb_host_unmatched"]

    def test_prsa_only_function_unchanged(self, catalogs):
        prsa, _, _ = catalogs
        tces = pd.DataFrame({"tic_id": [200], "orbital_period_days": [10.0]})
        out = add_period_matched_eb_labels(tces, prsa)
        assert bool(out.loc[0, "label_prsa_eb"]) and out.loc[0, "label_prsa_ratio"] == 2.0
