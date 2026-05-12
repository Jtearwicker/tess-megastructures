"""A4: SQLite state manifest.

Single source of truth for what's been downloaded, parsed, annotated,
and vetted. Lives at ``paths.manifest_path``.

Schema (created automatically on first use):

- ``sectors``: one row per (sector_run, run_type). Records expected
  TIC count, download status, parse status, and the version hashes
  of configs used.
- ``tic_downloads``: per-TIC download status. Useful for partial-failure
  recovery.
- ``parse_runs``: history of parse invocations. Each parse run records
  parser version (git SHA), config hash, input/output paths, row counts.
- ``annotation_runs``: history of annotation invocations. Records the
  filter and score config hashes.
- ``vetting_decisions``: see :mod:`tess_megastructures.vet.log`.

Concurrent writes from parallel Snakemake jobs are handled via
SQLite's WAL mode and short transactions.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def init_manifest(path: Path) -> sqlite3.Connection:
    """Initialize a manifest database at the given path.

    Creates tables if they don't exist. Idempotent.
    """
    raise NotImplementedError


def record_download(
    conn: sqlite3.Connection,
    sector_run: str,
    n_files_downloaded: int,
    n_files_failed: int,
) -> None:
    """Record a download invocation in the manifest."""
    raise NotImplementedError


def record_parse(
    conn: sqlite3.Connection,
    sector_run: str,
    parser_version: str,
    output_path: Path,
    n_tces: int,
) -> None:
    """Record a parse invocation in the manifest."""
    raise NotImplementedError
