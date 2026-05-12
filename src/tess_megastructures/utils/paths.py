"""Path resolution helpers.

Centralizes path construction so per-stage code never builds paths from
strings. All output paths flow through these helpers.
"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return the absolute path to the repository root.

    Determined by walking up from this file until a directory containing
    ``pyproject.toml`` is found.
    """
    raise NotImplementedError("To be implemented during repo scaffolding step.")


def configs_dir() -> Path:
    """Path to ``configs/`` at the repo root."""
    raise NotImplementedError("To be implemented during repo scaffolding step.")


def docs_dir() -> Path:
    """Path to ``docs/`` at the repo root."""
    raise NotImplementedError("To be implemented during repo scaffolding step.")
