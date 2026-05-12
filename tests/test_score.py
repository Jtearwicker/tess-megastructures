"""Tests for tess_megastructures.annotate.score."""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Implement after score module is real")
def test_score_increases_with_chisq():
    """Higher reduced chi-square => higher anomaly score (other things equal)."""
    pass


@pytest.mark.skip(reason="Implement after score module is real")
def test_score_handles_nan_inputs():
    """Score is NaN (not raised) for TCEs with missing inputs."""
    pass
