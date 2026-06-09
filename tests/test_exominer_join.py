"""Tests for the ExoMiner join (infer/exominer_join.py).

Covers the parts most likely to regress:
- sector-run formatting and the input(bare '55-55') vs uid('S55') reconciliation
  (the format mismatch that bit us against the real ExoMiner contract),
- median z-score = row-wise median of z_shape_*,
- the (tic_id, planet_number) <-> (target_id, tce_plnt_num) join, scoped per
  sector run, keeping all sample rows and leaving unscored rows NaN,
- missing-column errors.

All synthetic; no GPU, no network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tess_megastructures.infer import exominer_join as ej

# ----------------------------- run formatting -----------------------------


def test_sector_run_str_bare_integer_format():
    # ExoMiner's tic-list input wants bare '<start>-<end>', not 'S####'.
    assert ej._sector_run_str(55) == "55-55"
    assert ej._sector_run_str(58) == "58-58"
    assert ej._sector_run_str(np.int64(7)) == "7-7"


def test_sector_from_uid():
    assert ej._sector_from_uid("9155187-1-S47") == "S47"
    assert ej._sector_from_uid("123-2-S36-S69") == "S36-S69"
    assert ej._sector_from_uid("nope") is None
    assert ej._sector_from_uid(None) is None
    assert ej._sector_from_uid(float("nan")) is None


def test_normalize_run_reconciles_uid_and_sample_forms():
    # uid carries 'S'-prefixed run; sample side uses bare ints. Both must
    # normalize to the same bare form so the scoped join keys match.
    assert ej._normalize_run("S47") == "47-47"
    assert ej._normalize_run("S36-S69") == "36-69"
    assert ej._normalize_run(None) is None
    assert ej._normalize_run("garbage") is None
    # the round-trip that the join relies on:
    assert ej._normalize_run(ej._sector_from_uid("100-1-S55")) == ej._sector_run_str(55)


# ----------------------------- tic list -----------------------------


def test_write_exominer_tic_list_dedupes_and_formats(tmp_path):
    surv = pd.DataFrame(
        {
            "tic_id": [100, 200, 100],  # 100 appears twice (multi-TCE)
            "planet_number": [1, 1, 2],
            "sector": [55, 55, 55],
        }
    )
    out_path = tmp_path / "tics.csv"
    out = ej.write_exominer_tic_list(surv, out_path)
    # one row per unique (tic_id, sector_run); ExoMiner scores per target
    assert len(out) == 2
    assert sorted(out["tic_id"]) == [100, 200]
    assert set(out["sector_run"]) == {"55-55"}
    # file written and round-trips
    back = pd.read_csv(out_path)
    assert list(back.columns) == ["tic_id", "sector_run"]


def test_write_exominer_tic_list_missing_columns():
    with pytest.raises(KeyError):
        ej.write_exominer_tic_list(pd.DataFrame({"planet_number": [1]}), None)
    with pytest.raises(KeyError):
        ej.write_exominer_tic_list(pd.DataFrame({"tic_id": [1]}), None, sector_col="sector")


# ----------------------------- median z -----------------------------


def test_add_median_z_score_rowwise_median():
    df = pd.DataFrame(
        {
            "z_shape_0": [0.1, 0.2],
            "z_shape_1": [0.3, 0.4],
            "z_shape_2": [0.5, 0.9],
        }
    )
    out = ej.add_median_z_score(df)
    assert out[ej.MEDIAN_Z_COL].tolist() == [0.3, 0.4]


def test_add_median_z_score_no_z_columns_is_nan():
    out = ej.add_median_z_score(pd.DataFrame({"score": [0.5]}))
    assert ej.MEDIAN_Z_COL in out.columns
    assert out[ej.MEDIAN_Z_COL].isna().all()


# ----------------------------- merge -----------------------------


def _sample():
    return pd.DataFrame(
        {
            "tic_id": [100, 200, 300],
            "planet_number": [1, 1, 1],
            "sector": [55, 55, 55],
            "model_chi_square_reduced": [1.2, 1.5, 2.0],
        }
    )


def _predictions(tics=(100, 200)):
    rows = []
    for t in tics:
        rows.append(
            {
                "uid": f"{t}-1-S55",
                "target_id": t,
                "tce_plnt_num": 1,
                "tce_period": 4.0,
                "z_shape_0": 0.1,
                "z_shape_1": 0.3,
                "z_shape_2": 0.5,
                "score": 0.9 if t == 100 else 0.8,
            }
        )
    return pd.DataFrame(rows)


def test_merge_keeps_all_sample_rows_scores_matches():
    merged = ej.merge_predictions(_sample(), _predictions(), scope_by_sector_run=True)
    assert len(merged) == 3  # all sample rows kept
    assert merged.loc[merged.tic_id == 100, "score"].item() == 0.9
    assert merged.loc[merged.tic_id == 200, "score"].item() == 0.8
    # 300 was not scored -> NaN
    assert pd.isna(merged.loc[merged.tic_id == 300, "score"].item())
    # median z added
    assert ej.MEDIAN_Z_COL in merged.columns
    assert merged.loc[merged.tic_id == 100, ej.MEDIAN_Z_COL].item() == 0.3


def test_merge_scopes_by_sector_run():
    # a prediction in the WRONG run (S99) must not match the s55 sample row.
    sample = _sample().iloc[:1].copy()  # tic 100, sector 55
    preds = _predictions((100,)).copy()
    preds["uid"] = "100-1-S99"  # different run
    merged = ej.merge_predictions(sample, preds, scope_by_sector_run=True)
    assert pd.isna(merged["score"].iloc[0]), "should not match across sector runs"


def test_merge_unscoped_matches_regardless_of_run():
    sample = _sample().iloc[:1].copy()
    preds = _predictions((100,)).copy()
    preds["uid"] = "100-1-S99"
    merged = ej.merge_predictions(sample, preds, scope_by_sector_run=False)
    assert merged["score"].iloc[0] == 0.9


def test_merge_missing_key_columns_raise():
    with pytest.raises(KeyError):
        ej.merge_predictions(pd.DataFrame({"planet_number": [1]}), _predictions())
    with pytest.raises(KeyError):
        ej.merge_predictions(_sample(), pd.DataFrame({"tce_plnt_num": [1]}))


def test_merge_one_to_one_validation_catches_duplicates():
    # two prediction rows for the same (tic, planet, run) -> ambiguous, must raise
    sample = _sample().iloc[:1].copy()
    preds = pd.concat([_predictions((100,)), _predictions((100,))], ignore_index=True)
    with pytest.raises((ValueError, pd.errors.MergeError)):
        ej.merge_predictions(sample, preds, scope_by_sector_run=True)
