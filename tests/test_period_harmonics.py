"""Tests for tess_megastructures.annotate.period_harmonics."""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Implement after module is real")
def test_flags_identical_periods():
    """Two TCEs on the same TIC with the same period get flagged."""
    pass


@pytest.mark.skip(reason="Implement after module is real")
def test_flags_2to1_harmonic():
    """Two TCEs at P and 2P on the same TIC get flagged."""
    pass


@pytest.mark.skip(reason="Implement after module is real")
def test_does_not_flag_unrelated_periods():
    """Two TCEs at P and 1.5P (not in target ratios) don't get flagged."""
    pass


@pytest.mark.skip(reason="Implement after module is real")
def test_does_not_flag_across_different_tics():
    """Same period on different TICs is not a harmonic match."""
    pass
