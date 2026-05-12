"""Subsystem A: Sample and data ingest.

Handles:

- A1: Building the frozen parent stellar sample from TESS-SPOC FFI
  target lists and Doyle+24 stellar parameters.
- A2: Downloading TESS-SPOC DV XML files from MAST.
- A3: Parsing XML files into per-TCE Parquet tables.
- A4: Maintaining the SQLite state manifest.

The output of this subsystem is :func:`tces_master`, a Parquet table
with one row per TCE across all sectors in scope. This is the input
to :mod:`tess_megastructures.annotate`.
"""
