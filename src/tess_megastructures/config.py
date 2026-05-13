"""Configuration loading utilities.

All pipeline configs live as YAML files in the repository's ``configs/``
directory. This module provides a single entry point for loading them
and computes a content hash for provenance tracking.

Each output Parquet file should record the hash of the configs that
produced it; this allows downstream code (and the eventual paper) to
trace any number back to its exact configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file.

    Parameters
    ----------
    path : str or Path
        Path to the YAML file.

    Returns
    -------
    dict
        Parsed config as a nested dict.
    """
    raise NotImplementedError("To be implemented during repo scaffolding step.")


def config_hash(config: dict[str, Any]) -> str:
    """Compute a stable hash of a config dict.

    The hash is used as a provenance fingerprint on output artifacts,
    so it must be deterministic across runs and Python versions. We
    serialize with sorted keys and hash the bytes.

    Parameters
    ----------
    config : dict
        Parsed config dict.

    Returns
    -------
    str
        Hex-encoded SHA-256 hash, truncated to 16 chars.
    """
    raise NotImplementedError("To be implemented during repo scaffolding step.")


def load_paths() -> dict[str, str]:
    """Load the per-machine paths config.

    Looks for ``configs/paths.yaml`` (gitignored) at the repo root.
    Falls back to ``configs/paths.example.yaml`` with a warning if the
    machine-specific file doesn't exist (useful for tests and CI).
    """
    raise NotImplementedError("To be implemented during repo scaffolding step.")
