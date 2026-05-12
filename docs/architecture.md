# Architecture

This document is the design reference for the pipeline. It is normative
for v1; substantive deviations should be discussed and recorded in
`docs/decisions.md`.

## Project staging

This is a multi-paper effort delivered in three versions:

- **v1 — Anomaly catalog (~9 months).** A vetted catalog of TESS-SPOC
  TCEs that don't fit standard astrophysical explanations. Periodic
  signals only. Output is a candidate list with vetting decisions.
- **v2 — Upper limits (~18 months).** Occurrence-rate constraints on
  periodic megastructure transit signatures. Adds rigorous injection-
  recovery and the statistical inference layer.
- **v3 — Aperiodic search (post-v2).** Custom light-curve search for
  Boyajian-style irregular dimming.

The codebase targets v1. v2 and v3 namespaces (`infer/`, `inject/`)
exist as placeholders.

## Subsystem overview

The pipeline is four loosely-coupled subsystems plus an injection-
recovery system that runs in parallel for v2:

```
+-----------------+    +-----------------+    +-----------------+    +-----------------+
| A. Sample &     |--->| B. Signal       |--->| C. Vetting &    |--->| D. Statistical  |
|    data ingest  |    |    annotation   |    |    classification |    |    inference   |
+-----------------+    +-----------------+    +-----------------+    +-----------------+
                              ^
                              |
                       +------+-------+
                       | Injection-   |
                       | recovery     |
                       | (v2 parallel)|
                       +--------------+
```

Each subsystem produces a versioned, persistent artifact. Subsystems
communicate by reading and writing Parquet files, never by passing
in-memory state.

## Subsystem details

See `docs/per_subsystem/A_ingest.md`, `B_annotate.md`, `C_vet.md`,
`D_infer.md` for per-subsystem detail.

## Cross-cutting design choices

### Boolean filter columns

Stage B never drops rows. Every filter is a boolean column on the
master TCE table. This preserves the rejected sample for v2 detection
efficiency calculations and lets us re-tune filter thresholds without
re-parsing data.

### Frozen parent sample

The denominator for v2 occurrence rates is `parent_sample_v1.parquet`,
built once and never modified. If cuts need to change, we bump to v2.

### Configuration in YAML

All thresholds, weights, and selection cuts live in `configs/*.yaml`.
Output Parquets record the hash of the config that produced them.

### Vetting protocol pre-registered

The classification taxonomy and decision rules live in
`docs/vetting_protocol_v1.md`. This document is finalized before
main vetting begins and cited in the paper.

### Snakemake orchestration

Per-stage parallelism, dependency tracking, and cluster submission go
through Snakemake. Rules in `workflow/rules/`, profiles in
`workflow/profiles/`.

## What this design avoids

- **Reading FITS light curves in v1.** The TCE-list-only scope is
  faster to build and gets us to a publishable v1 result on schedule.
  v2 will add light-curve-level work for injection-recovery; v3 for
  custom aperiodic search.
- **Custom transit fitting.** We trust SPOC's fit quality; our value-add
  is in filtering, scoring, and vetting, not re-fitting.
- **Real-time updates.** The pipeline is batch. Snakemake re-runs
  produce updated outputs, but we don't aim for streaming.

## What this design defers to v2

- Detection efficiency: η(signal_params, stellar_params).
- Sample completeness corrections beyond the parent-sample cuts.
- Upper limits and posteriors.
- Sensitivity maps.

The v1 architecture is structured so v2 work plugs in cleanly without
restructuring.

## What this design defers to v3

- Aperiodic / irregular-dimming search (Boyajian-class signals).
- Custom transit search algorithms beyond what SPOC provides.

These will likely require their own ingest pipeline (FFI light curves
rather than TCE XML); the v1 architecture intentionally does not
constrain that future design.
