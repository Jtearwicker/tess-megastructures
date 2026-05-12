"""Shared pytest fixtures and configuration."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def example_xml(fixtures_dir: Path) -> Path:
    """Path to the canonical example DV XML file used in parser tests."""
    return fixtures_dir / "example_dv.xml"
