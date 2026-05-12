"""Subsystem B: TCE annotation.

Adds derived metrics, catalog cross-matches, filter flags, and an
anomaly score to the master TCE table without ever discarding rows.
This preserves the rejected sample for v2 detection-efficiency
calculations.

Module organization:

- :mod:`.derived_metrics`  — B1: computed quantities from extracted DV fields.
- :mod:`.period_harmonics` — B2: flag TICs with related-period TCEs.
- :mod:`.catalog_xmatch`   — B3: cross-match against literature catalogs.
- :mod:`.simbad_xmatch`    — B4: SIMBAD object types.
- :mod:`.filters`          — B5: boolean filter columns.
- :mod:`.score`            — B6: anomaly score for prioritizing vetting.

Output: ``tces_annotated_v1.parquet``, same row count as the master
TCE table with ~30 additional columns.
"""
