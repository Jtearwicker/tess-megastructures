"""Tests for non-destructive CTOI/VSX review routing."""

from __future__ import annotations

import pandas as pd
import pytest

from tess_megastructures.annotate.review_routing import add_catalog_review_routes


def _sample() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "tic_id": range(1, 8),
            "planet_number": [1] * 7,
            "sector": [42] * 7,
            "any_diagnostic_flag": [False, True, False, True, False, True, False],
            "in_clean_sample": [True, False, True, False, True, False, True],
        }
    )


def test_route_precedence_and_no_automatic_veto():
    enrichment = pd.DataFrame(
        [
            {
                "tic_id": 1,
                "planet_number": 1,
                "sector": 42,
                "label": "planet",
                "vsx_signal_match": True,
                "vsx_types": "EA",
            },
            {
                "tic_id": 2,
                "planet_number": 1,
                "sector": 42,
                "ctoi_signal_match": True,
                "ctoi_dispositions": "PC",
                "vsx_signal_match": True,
                "vsx_types": "EA",
            },
            {
                "tic_id": 3,
                "planet_number": 1,
                "sector": 42,
                "ctoi_signal_match": True,
                "ctoi_dispositions": "FP",
            },
            {
                "tic_id": 4,
                "planet_number": 1,
                "sector": 42,
                "vsx_signal_match": True,
                "vsx_types": "EW",
            },
            {
                "tic_id": 5,
                "planet_number": 1,
                "sector": 42,
                "vsx_signal_match": True,
                "vsx_types": "RRAB",
            },
            {"tic_id": 6, "planet_number": 1, "sector": 42, "ctoi_host_match": True},
        ]
    )
    original = _sample()
    out = add_catalog_review_routes(original, enrichment)

    assert out["catalog_review_route"].tolist() == [
        "protect_confirmed_planet",
        "protect_planet_candidate",
        "review_known_toi_fp",
        "review_catalog_eb",
        "review_period_matched_variable",
        "review_catalog_context",
        "standard_review",
    ]
    assert not out["catalog_automatic_veto"].any()
    assert out["any_diagnostic_flag"].equals(original["any_diagnostic_flag"])
    assert out["in_clean_sample"].equals(original["in_clean_sample"])


def test_no_enrichment_produces_stable_standard_review_schema():
    out = add_catalog_review_routes(_sample(), None)
    assert set(out["catalog_review_route"]) == {"standard_review"}
    assert set(out["catalog_route_schema_version"]) == {"1.0.0"}
    assert not out["catalog_automatic_veto"].any()


def test_existing_label_is_preserved_when_enrichment_omits_it():
    sample = _sample().iloc[:1].assign(label="planet")
    enrichment = pd.DataFrame(
        {"tic_id": [1], "planet_number": [1], "sector": [42], "vsx_signal_match": [True]}
    )
    out = add_catalog_review_routes(sample, enrichment)
    assert out.loc[0, "label"] == "planet"
    assert out.loc[0, "catalog_review_route"] == "protect_confirmed_planet"


def test_duplicate_tce_keys_are_rejected():
    duplicate = pd.DataFrame({"tic_id": [1, 1], "planet_number": [1, 1], "sector": [42, 42]})
    with pytest.raises(ValueError, match="duplicate rows"):
        add_catalog_review_routes(_sample(), duplicate)
