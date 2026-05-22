# Architecture

This document is the design reference for the pipeline. It is normative
for v1; substantive deviations should be discussed and recorded in
`docs/decisions.md`.

> Scope note: v1 has changed direction more than once (see decisions.md).
> The current plan of record (2026-05-20) is the **MegaMiner** ML-driven
> candidate pipeline. This document describes that plan. Some details
> (this project's exact first-author contribution, the timeline, the
> agentic-orchestration choice) are still being resolved and are marked
> TODO; the overall direction is committed.

## Project staging

This is a multi-paper effort.

- **v1 — MegaMiner candidate catalog.** An ML-driven search over the
  full SPOC FFI TCE population (~1M TCEs), narrowing to a vetted catalog
  of anomalous candidates framed around megastructure signatures. The
  headline deliverable is a candidate catalog (not an occurrence rate).
- **v2 — Upper limits (future).** Occurrence-rate / upper-limit
  constraints on megastructure signatures. Requires the stellar parent
  sample (Definition A), injection-recovery, and detection-efficiency
  characterization — all deferred from v1. v1's vetted catalog becomes
  validation input for v2.
- **v3 — Aperiodic search (later).** Custom light-curve search for
  Boyajian-style irregular dimming. Different ingest pipeline; a
  separable effort.

The codebase currently targets v1.

## The MegaMiner pipeline (v1)

```
~1M TCEs                                                vetted
(SPOC FFI)                                            candidate catalog
   |                                                         ^
   v                                                         |
[Manual cuts] -> [ExoMiner score] -> [Autoencoder    ] -> [LLM-based] -> [vetting]
                  + EB/Z score        anomaly detector     triage
   ^                  ^                   ^                    ^
   |                  |                   |                    |
 ours            external (NASA)     collaborators        scope TBD
                                     (NASA Ames)
                 (agentic orchestration: deferred; no tool committed)
```

The headline v1 deliverable is the vetted candidate catalog. The pipeline
INPUT is the TCE population (Definition B; see below). Component ownership
and maturity are recorded in decisions.md (2026-05-20 MegaMiner entry).

## Sample definitions: B (v1) vs A (v2)

Two distinct populations, easily confused:

- **Definition B — TCE population (v1).** Every SPOC FFI TCE, aggregated
  across sectors. This is what MegaMiner operates on. Built by
  `ingest/tce_sample.py` -> `tce_sample_v1.parquet`. The relevant
  "how many did we start from" count for a candidate catalog.
- **Definition A — stellar parent sample (v2).** Every SEARCHED star,
  including those that produced no TCE. The denominator for an
  occurrence-rate/upper-limit claim. Deferred to v2. The
  `ingest/parent_sample.py` stub is a placeholder for this.

v1 uses B. "Parent sample" refers specifically to A and is not built yet.

## Signal framing

v1 is framed around Wright+16 megastructure transit signatures (asymmetric
shapes, depth variation, anomalous depth/duration). In v1 these motivate
the anomaly search and the candidate scoring/taxonomy; they are NOT used
to compute per-class detection efficiencies (that is v2 upper-limits work).
The known-anomaly validation set (disintegrating planets, dippers,
Boyajian analogs) is used to confirm the pipeline recovers genuinely
anomalous objects.

## Subsystem overview

```
+------------------+   +------------------+   +------------------+
| A. Sample &      |-->| B. Annotation &  |-->| C. Vetting &     |
|    data ingest   |   |    ML scoring    |   |    classification|
+------------------+   +------------------+   +------------------+
```

- **A. Ingest.** Download DV XML, parse to per-sector Parquet, aggregate
  into the Definition-B TCE sample with stellar params and cuts.
- **B. Annotation & ML scoring.** Derived metrics + boolean filter
  columns (manual cuts), then ML scores: ExoMiner, EB/Z, autoencoder
  anomaly score. Never drops rows.
- **C. Vetting & classification.** Candidate selection by query over the
  annotated table, LLM-assisted triage (scope TBD), human vetting with a
  documented protocol, producing the catalog.

Inject (injection-recovery) and Infer (statistical inference) subsystems
are **v2** (upper limits) and not part of v1.

Each subsystem produces a versioned, persistent Parquet artifact.
Subsystems communicate by reading/writing Parquet, never by passing
in-memory state.

## Implementation status

As of 2026-05-20:

- **A3 (XML parsing):** implemented and tested.
  `ingest/parse.py`, `tests/test_parse.py`. 26 tests, 83% coverage.
  Smoke test against committed fixture (TIC 307210830 sector 63),
  68-column schema in `data_dictionary.md`.
- **A (TCE sample, Definition B):** implemented and tested.
  `ingest/tce_sample.py`, `tests/test_tce_sample.py`. 16 tests against
  synthetic data. Not yet wired to real parsed sectors (built under
  "Order B" — develop against synthetic, wire to real data later).
- **A2 (XML download):** scaffolded stub.
- **A (parent sample, Definition A):** placeholder stub; v2.
- **Catalog loaders (`catalogs/`):** stubs. Doyle+24 loader is the next
  planned piece (enables the TCE sample's Doyle enrichment).
- **B (annotation + ML scoring):** scaffolded stubs. ExoMiner /
  autoencoder integration not yet started.
- **C (vetting):** scaffolded stubs.
- **Inject / Infer:** placeholders; v2.

## Cross-cutting design choices

### Boolean filter columns

Annotation never drops rows. Every filter is a boolean column. Preserves
the rejected sample (useful for v2 detection efficiency) and lets filter
thresholds change without re-parsing. Candidate selection is a query over
the boolean columns.

### Definition-B TCE sample, not a parent sample (v1)

v1's sample is the TCE population (`tce_sample_v1.parquet`), built once
and versioned. The stellar parent sample (Definition A) is a v2 artifact.
See decisions.md.

### External / collaborator ML components

ExoMiner (NASA) and the autoencoder (NASA Ames collaborators) are
imported, not built here. This project owns the manual cuts, the science
framing, the signal taxonomy, the known-anomaly validation set, and
candidate vetting. LLM triage scope is TBD; agentic orchestration is
deferred. See decisions.md (MegaMiner entry) for ownership detail.

### Configuration in YAML

Thresholds, cuts, and selection parameters live in `configs/*.yaml`.
Cut VALUES are placeholders pending a science decision; the code reads
them from config so finalizing is a one-line edit. Output Parquets should
record the config version/hash that produced them.

### Validate locally before the node

Develop + test locally (pytest + ruff) -> push -> CI green (3.11/3.12)
-> `git pull` on tarang-node1. The node runs only validated code; heavy
scale runs happen there after small-input validation. See decisions.md.

### Schema stability

Parser output columns are documented in `data_dictionary.md`. Columns may
be added; existing columns must not change name/dtype. The smoke test in
`tests/test_parse.py` catches accidental schema changes against a
committed `tests/fixtures/expected_parse.json`. To change the schema
intentionally: run `scripts/regenerate_parse_fixture.py`, review the diff,
update the data dictionary in the same commit.

### Snakemake orchestration

Per-stage parallelism and dependency tracking via Snakemake. Note:
tarang-node1 has no scheduler (direct SSH, single dedicated node), so the
SLURM profile is currently unused; Snakemake still provides the DAG and
local parallelism.

## What this design avoids

- **Reading FITS light curves except where required** (autoencoder
  scoring, eventual vetting plots). TCE metadata is the primary input to
  the early stages.
- **Custom transit fitting.** SPOC's fits are trusted; value-add is in
  filtering, ML scoring, vetting, and the science framing.
- **Real-time updates.** Batch pipeline.

## What this design defers to v2

- Stellar parent sample (Definition A) and occurrence-rate / upper-limit
  calculations.
- Injection-recovery, MES proxy, detection-efficiency characterization.
- Per-class Wright+16 detection efficiencies.

## What this design defers to v3

- Aperiodic / irregular-dimming search (Boyajian-class signals), which
  needs its own FFI-light-curve ingest pipeline.

## Open questions (tracked in decisions.md)

- This project's specific first-author contribution within the
  multi-person MegaMiner effort.
- Timeline.
- LLM-triage scope (assistant vs. classifier).
- Agentic-orchestration tool and whether it is in v1 at all.
- Whether an ExoMiner FFI score catalog already exists (arXiv 2601.14877)
  vs. running ExoMiner ourselves.
