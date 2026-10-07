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
from datetime import datetime, timezone
from pathlib import Path


def _utcnow() -> str:
    """ISO8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def init_manifest(path: Path) -> sqlite3.Connection:
    """Initialize a manifest database at the given path.

    Creates tables if they don't exist. Idempotent. Enables WAL mode so
    parallel Snakemake jobs can write concurrently without locking each
    other out.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    # WAL: concurrent readers + one writer without blocking; survives crashes.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sectors (
            sector_run      TEXT NOT NULL,
            run_type        TEXT NOT NULL DEFAULT 'single',  -- 'single' | 'multi'
            expected_tics   INTEGER,
            n_downloaded    INTEGER,
            n_failed        INTEGER,
            download_status TEXT DEFAULT 'pending',  -- pending|complete|failed
            parse_status    TEXT DEFAULT 'pending',  -- pending|complete|failed
            config_hash     TEXT,
            updated_at      TEXT,
            PRIMARY KEY (sector_run, run_type)
        );

        CREATE TABLE IF NOT EXISTS tic_downloads (
            sector_run   TEXT NOT NULL,
            tic_id       INTEGER NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending',  -- pending|ok|failed
            n_files      INTEGER DEFAULT 0,
            updated_at   TEXT,
            PRIMARY KEY (sector_run, tic_id)
        );

        CREATE TABLE IF NOT EXISTS parse_runs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            sector_run     TEXT NOT NULL,
            parser_version TEXT,
            config_hash    TEXT,
            output_path    TEXT,
            n_tces         INTEGER,
            created_at     TEXT
        );

        CREATE TABLE IF NOT EXISTS annotation_runs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            sector_run    TEXT,
            filter_hash   TEXT,
            score_hash    TEXT,
            output_path   TEXT,
            n_rows        INTEGER,
            created_at    TEXT
        );
        """
    )
    conn.commit()
    return conn


def record_download(
    conn: sqlite3.Connection,
    sector_run: str,
    n_files_downloaded: int,
    n_files_failed: int,
) -> None:
    """Record a download invocation in the manifest.

    Upserts the ``sectors`` row for this sector_run, setting download
    counts and a status of 'complete' (no failures) or 'failed'.
    """
    status = "complete" if n_files_failed == 0 else "failed"
    now = _utcnow()
    with conn:  # transaction: commit on success, rollback on error
        conn.execute(
            """
            INSERT INTO sectors (sector_run, n_downloaded, n_failed,
                                 download_status, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(sector_run, run_type) DO UPDATE SET
                n_downloaded    = excluded.n_downloaded,
                n_failed        = excluded.n_failed,
                download_status = excluded.download_status,
                updated_at      = excluded.updated_at
            """,
            (sector_run, n_files_downloaded, n_files_failed, status, now),
        )


def record_parse(
    conn: sqlite3.Connection,
    sector_run: str,
    parser_version: str,
    output_path: Path,
    n_tces: int,
) -> None:
    """Record a parse invocation in the manifest.

    Appends a row to ``parse_runs`` (history is preserved across re-parses)
    and updates the sector's ``parse_status`` to 'complete'.
    """
    now = _utcnow()
    with conn:
        conn.execute(
            """
            INSERT INTO parse_runs (sector_run, parser_version, output_path,
                                    n_tces, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sector_run, parser_version, str(output_path), n_tces, now),
        )
        # ensure a sectors row exists, then mark parse complete
        conn.execute(
            """
            INSERT INTO sectors (sector_run, parse_status, updated_at)
            VALUES (?, 'complete', ?)
            ON CONFLICT(sector_run, run_type) DO UPDATE SET
                parse_status = 'complete',
                updated_at   = excluded.updated_at
            """,
            (sector_run, now),
        )
