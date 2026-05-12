"""C5: SQLite-backed vetting log.

Stores one row per (candidate, vetter, vetting_round). The log is the
authoritative record of what classifications were made and is the
basis for the v1 paper's candidate count claims.

CRITICAL: this database is hard to regenerate (it's the result of
hundreds of hours of human work). Back it up regularly. The path is
configured in ``configs/paths.yaml`` with the expectation that it
lives in a backed-up location.

Schema:

    candidate_id       TEXT     -- unique candidate identifier
    vetter_id          TEXT     -- usually initials or username
    vetting_round      INTEGER  -- 1 = initial, 2 = re-vet, etc.
    classification     TEXT     -- see classification taxonomy below
    confidence         TEXT     -- 'low' | 'medium' | 'high'
    wright16_match     TEXT     -- which Wright+16 signature(s), if any
    notes              TEXT     -- free-text
    timestamp          DATETIME
    package_version    TEXT     -- hash of the package files vetted
    config_hash        TEXT     -- annotation config hash for traceability

Classification taxonomy (see docs/vetting_protocol_v1.md for definitions):

    planet
    eb_missed
    instrumental
    background
    known_variable
    unexplained_uninteresting
    unexplained_interesting
    megastructure_candidate
    unsure
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

CLASSIFICATION_VALUES = (
    "planet",
    "eb_missed",
    "instrumental",
    "background",
    "known_variable",
    "unexplained_uninteresting",
    "unexplained_interesting",
    "megastructure_candidate",
    "unsure",
)

ConfidenceLevel = Literal["low", "medium", "high"]


def init_log(path: Path) -> sqlite3.Connection:
    """Create the vetting log database if it doesn't exist."""
    raise NotImplementedError


def record_decision(
    conn: sqlite3.Connection,
    candidate_id: str,
    vetter_id: str,
    vetting_round: int,
    classification: str,
    confidence: ConfidenceLevel,
    wright16_match: str = "",
    notes: str = "",
) -> None:
    """Record a vetting decision.

    Validates that ``classification`` is in :data:`CLASSIFICATION_VALUES`.
    """
    raise NotImplementedError


def get_decisions_for(
    conn: sqlite3.Connection,
    candidate_id: str,
) -> list[dict]:
    """All decisions recorded for a candidate, across vetters and rounds."""
    raise NotImplementedError
