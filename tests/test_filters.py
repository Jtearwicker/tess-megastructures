"""Tests for tess_megastructures.annotate.filters.

Pattern: construct a synthetic TCE table with known values, apply
the filters with a known config, assert that the boolean columns
match expectation.

This is the test that catches "I bumped a threshold and forgot what
it should do" bugs.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Implement after filters module is real")
def test_failed_convergence_when_not_converged():
    pass


@pytest.mark.skip(reason="Implement after filters module is real")
def test_passes_all_filters_is_and_of_failed_columns():
    pass


@pytest.mark.skip(reason="Implement after filters module is real")
def test_filter_does_not_drop_rows():
    """The most important property: filter stage preserves row count."""
    pass


@pytest.mark.skip(reason="Implement after filters module is real")
def test_thresholds_come_from_config():
    """Changing the config changes the filter outcome."""
    pass
