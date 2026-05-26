"""Path resolution helpers.

Centralizes path construction so per-stage code never builds paths from
strings. All output paths flow through these helpers.

Per-machine paths (where raw data lives, where to write outputs, where the
Doyle+24 catalog is, etc.) are configured in ``configs/paths.yaml`` — a
gitignored, machine-specific file copied from ``paths.example.yaml``.
``load_paths()`` reads it into a dict.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Return the absolute path to the repository root.

    Determined by walking up from this file until a directory containing
    ``pyproject.toml`` is found.

    Raises
    ------
    RuntimeError
        If no ``pyproject.toml`` is found in any parent directory.
    """
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(
        f"Could not locate repo root (no pyproject.toml found in any parent of {here})."
    )


def configs_dir() -> Path:
    """Path to ``configs/`` at the repo root."""
    return repo_root() / "configs"


def docs_dir() -> Path:
    """Path to ``docs/`` at the repo root."""
    return repo_root() / "docs"


def load_paths(paths_file: Path | None = None) -> dict[str, Any]:
    """Load per-machine path configuration from ``configs/paths.yaml``.

    Parameters
    ----------
    paths_file : Path, optional
        Explicit path to a paths YAML file. Defaults to
        ``configs/paths.yaml`` at the repo root.

    Returns
    -------
    dict
        Mapping of path keys (e.g. ``"doyle2024_catalog"``, ``"xml_dir"``,
        ``"processed_data_dir"``) to string path values, as written in the
        YAML file.

    Raises
    ------
    FileNotFoundError
        If the paths file does not exist. The message points the user at
        the copy-from-example step, since this is the most common setup
        mistake on a fresh machine.
    """
    if paths_file is None:
        paths_file = configs_dir() / "paths.yaml"
    paths_file = Path(paths_file)

    if not paths_file.is_file():
        example = configs_dir() / "paths.example.yaml"
        raise FileNotFoundError(
            f"Path config not found: {paths_file}\n"
            f"Create it for this machine by copying the template:\n"
            f"    cp {example} {paths_file}\n"
            f"then edit the paths for this machine."
        )

    with open(paths_file) as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(f"{paths_file} did not parse to a mapping of keys to paths.")

    return data
