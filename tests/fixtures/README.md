# Test fixtures

Small files used by the test suite. Committed to the repo so tests are
fully reproducible without external downloads.

## What goes here

- `example_dv.xml` — A canonical DV XML file used by parser tests.
  To be added during the parser refactor stage. Pick a TIC whose XML
  exercises a representative set of DV elements (multiple TCEs, valid
  centroid data, EB suspicion flag set, etc.).
- `expected_parse.json` — The expected parser output for `example_dv.xml`.
  Captured once, regenerated only when the parser schema intentionally
  changes (and reviewed in PR).

## What does NOT go here

- Real catalog files (Prsa, Kostov, etc.) — too large, lives in
  `data/literature/` (gitignored).
- FFI light curves — much too large.
- Vetting log dumps — these are outputs, not fixtures.
