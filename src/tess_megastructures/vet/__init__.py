"""Subsystem C: Candidate vetting.

Selects candidates from the annotated TCE table, generates per-candidate
review packages, and provides a structured log for human classifications.

Module organization:

- :mod:`.candidates` — C1: candidate selection from filter+score outputs.
- :mod:`.packages`   — C2: generate per-candidate review packages
                       (DV PDFs, light curve plots, summary cards).
- :mod:`.log`        — C5: SQLite-backed vetting log read/write.

The vetting interface itself lives in ``apps/vetting_app/`` and uses
this package's primitives.
"""
