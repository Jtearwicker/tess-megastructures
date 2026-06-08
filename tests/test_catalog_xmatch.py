"""Tests for the catalog cross-match (vetted flags + unvetted annotation)."""

from __future__ import annotations

import pandas as pd

from tess_megastructures.annotate.catalog_xmatch import (
    CATALOG_EB_FLAG,
    add_catalog_flags,
)


def _catalog(tics: list[int]) -> pd.DataFrame:
    """Minimal loader-shaped frame: just the ticId column the xmatch needs."""
    return pd.DataFrame({"ticId": tics})


def _sample(tic_ids: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"tic_id": tic_ids, "planet_number": [1] * len(tic_ids)})


class TestCatalogFlags:
    def test_vetted_membership_sets_flag(self):
        df = _sample([100, 200, 999])
        out = add_catalog_flags(
            df,
            prsa=_catalog([100]),
            kostov_vetted=_catalog([200]),
            kostov_unvetted=None,
        )
        assert bool(out.loc[out.tic_id == 100, "flag_prsa_eb"].item())
        assert bool(out.loc[out.tic_id == 200, "flag_kostov_eb"].item())
        assert bool(out.loc[out.tic_id == 100, CATALOG_EB_FLAG].item())
        assert bool(out.loc[out.tic_id == 200, CATALOG_EB_FLAG].item())
        assert not bool(out.loc[out.tic_id == 999, CATALOG_EB_FLAG].item())

    def test_combined_flag_is_union(self):
        df = _sample([1, 2, 3])
        out = add_catalog_flags(
            df,
            prsa=_catalog([1]),
            kostov_vetted=_catalog([2]),
            kostov_unvetted=None,
        )
        # combined vetted flag = prsa OR kostov
        assert bool(out.loc[out.tic_id == 1, CATALOG_EB_FLAG].item())
        assert bool(out.loc[out.tic_id == 2, CATALOG_EB_FLAG].item())
        assert not bool(out.loc[out.tic_id == 3, CATALOG_EB_FLAG].item())

    def test_unvetted_is_annotation_not_flag(self):
        # A TIC ONLY in the unvetted list must be annotated but NOT flagged.
        df = _sample([700])
        out = add_catalog_flags(
            df,
            prsa=None,
            kostov_vetted=None,
            kostov_unvetted=_catalog([700]),
        )
        assert bool(out.loc[out.tic_id == 700, "annotation_kostov_candidate"].item())
        assert not bool(out.loc[out.tic_id == 700, CATALOG_EB_FLAG].item())
        # annotation must not be a flag_ column (won't enter any_diagnostic_flag)
        assert "annotation_kostov_candidate".startswith("annotation_")

    def test_missing_catalog_degrades_gracefully(self):
        # All catalogs None -> all flags False, no crash, rows preserved.
        df = _sample([1, 2, 3])
        out = add_catalog_flags(df, prsa=None, kostov_vetted=None, kostov_unvetted=None)
        assert len(out) == 3
        assert out["flag_prsa_eb"].sum() == 0
        assert out["flag_kostov_eb"].sum() == 0
        assert out[CATALOG_EB_FLAG].sum() == 0
        assert out["annotation_kostov_candidate"].sum() == 0

    def test_rows_never_dropped(self):
        df = _sample([1, 2, 3, 4, 5])
        out = add_catalog_flags(df, prsa=_catalog([1]), kostov_vetted=_catalog([2]))
        assert len(out) == len(df)

    def test_requires_tic_id(self):
        df = pd.DataFrame({"not_tic": [1, 2]})
        try:
            add_catalog_flags(df, prsa=_catalog([1]))
            raise AssertionError("should have raised KeyError")
        except KeyError:
            pass
