# Architecture

This document is the design reference for the pipeline. It is normative
for v1; substantive deviations should be discussed and recorded in
`docs/decisions.md`.

## Project staging

This is a multi-paper effort. v1 scope was revised on 2026-05-13 (see
decisions.md); the current plan is:

- **v1 — Upper limits paper (~12–18 months).** Upper limits on
  megastructure occurrence rate, marginalized over a small number of
  Wright+16 periodic transit signature classes. Output is a published
  catalog of vetted candidates (a byproduct) plus the headline
  statistical claim.
- **v2 — Extended signal coverage (post-v1).** Additional signature
  classes, expanded multi-sector coverage, possibly Path A
  injection-recovery rigor as a methodology paper.
- **v3 — Aperiodic search (later).** Custom light-curve search for
  Boyajian-style irregular dimming. Different ingest pipeline; a
  separable effort.

The codebase currently targets v1.

## v1 deliverable

A defensible upper limit requires four things, each of which maps onto
a subsystem (see below):

1. **A frozen parent sample** — explicit denominator. "We searched
   *N* stars with these properties." (Subsystem A.)
2. **A defined search** — what signals could have been detected.
   Encoded as SPOC's TCE detection plus our filter chain. (Subsystems
   A and B.)
3. **A characterized detection efficiency** — η(signal params,
   stellar params). What fraction of real signals would have survived
   to be candidates. (Inject module.)
4. **A defended candidate count** — *k*. Real candidates, vetted
   with documented protocol. (Subsystem C.)

The upper limit is then a Poisson-style bound on the rate given
*k*, *N*, and η.

## Signal classes for v1

v1 covers three to four Wright+16 periodic transit signature classes:

1. Standard transits at anomalous parameters (deep, low-density,
   wrong duration for inferred planet size).
2. Depth-varying transits (Arnold beacon-style; KIC 1255b dust-tail
   analogs).
3. Asymmetric / non-circular transit shapes (Arnold artificial
   silhouettes).
4. One additional class TBD, likely anomalous depth-duration ratio.

A single combined upper limit, marginalized across these classes
with uniform priors, is the headline statistic. Per-class limits
and parameter-binned sensitivity maps are reported but not the
headline number.

## Subsystem overview

```
+------------------+   +------------------+   +------------------+   +------------------+
| A. Sample &      |-->| B. Signal        |-->| C. Vetting &     |-->| D. Statistical  |
|    data ingest   |   |    annotation    |   |    classification|   |    inference     |
+------------------+   +------------------+   +------------------+   +------------------+
                              ^                                          ^
                              |                                          |
                       +------+-------+                                  |
                       | Inject:      |--------------------------------->|
                       | signals +    |   eta(theta, stellar) table
                       | recovery     |
                       +--------------+
```

Each subsystem produces a versioned, persistent artifact. Subsystems
communicate by reading and writing Parquet files, never by passing
in-memory state.

The injection-recovery system is part of v1 (not v2 as originally
planned). It reuses subsystem B's annotation code on synthetic
signals so that real and injected signals pass through identical
filters; this is what makes η valid for the upper-limit calculation.

## Subsystem details

See `docs/per_subsystem/A_ingest.md`, `B_annotate.md`, `C_vet.md`,
`D_infer.md` for per-subsystem detail.

## Implementation status

As of 2026-05-13:

- **A1 (parent sample):** scaffolded, not yet implemented.
- **A2 (XML download):** scaffolded, not yet implemented.
- **A3 (XML parsing):** **implemented and tested.** See
  `src/tess_megastructures/ingest/parse.py` and `tests/test_parse.py`.
  Smoke test against committed fixture (TIC 307210830 sector 63)
  validates 68 output columns across 3 TCEs.
- **A4 (state manifest):** scaffolded, not yet implemented.
- **B (annotation):** scaffolded; modules are stubs.
- **C (vetting):** scaffolded; Streamlit app is a stub.
- **D (inference):** placeholder only.
- **Inject (injection-recovery):** placeholder only.

## Cross-cutting design choices

### Boolean filter columns

Stage B never drops rows. Every filter is a boolean column on the
master TCE table. This preserves the rejected sample for detection
efficiency calculations and lets us re-tune filter thresholds without
re-parsing data. Candidate selection (C1) is a separate query over
the boolean columns.

### Frozen parent sample

The denominator for the upper-limits calculation is
`parent_sample_v1.parquet`, built once and never modified. If cuts
need to change, we bump to a new file (e.g., `parent_sample_v2.parquet`).
Output Parquets that depend on the parent sample record which version
they used.

### Detection efficiency: Path B with calibration

η is computed via a documented MES proxy (not a full SPOC pipeline
replica). The calibration appendix — comparing proxy MES against
SPOC's reported MES — is a first-class output of the project. The
upper limit must be robust to plausible miscalibration of the proxy.
See decisions.md for the calibration plan.

### Configuration in YAML

All thresholds, weights, selection cuts, and signal-class parameter
ranges live in `configs/*.yaml`. Output Parquets record the hash of
the config that produced them so any number in the paper can be
traced to its source.

### Vetting protocol pre-registered

The classification taxonomy and decision rules live in
`docs/vetting_protocol_v1.md`. Finalized before main vetting begins
and cited in the paper. For an upper-limits paper, the vetting bar
is higher than for a candidate catalog — every survivor counts in
the *k*.

### Snakemake orchestration

Per-stage parallelism, dependency tracking, and cluster submission go
through Snakemake. Rules in `workflow/rules/`, profiles in
`workflow/profiles/`.

### Schema stability

Parser output columns are documented in `docs/data_dictionary.md`.
Columns may be added; existing columns must not change name or dtype.
The smoke test in `tests/test_parse.py` catches accidental schema
changes by comparing parser output against a committed
`tests/fixtures/expected_parse.json`. To intentionally change the
schema: run `scripts/regenerate_parse_fixture.py`, review the diff,
update the data dictionary in the same commit.

## What this design avoids

- **Reading FITS light curves except for injection-recovery.** TCE
  metadata is the primary input. Light curves are downloaded only for
  the subset of stars used in injection-recovery, and (eventually) for
  vetting plots of candidates.
- **Custom transit fitting.** We trust SPOC's fit quality; our value-add
  is in filtering, scoring, vetting, and the statistical layer — not
  re-fitting.
- **Real-time updates.** The pipeline is batch. Snakemake re-runs
  produce updated outputs, but we don't aim for streaming.

## What this design defers to v2+

- Additional Wright+16 signature classes beyond the v1 four.
- Multi-sector run handling beyond single-sector results.
- Possibly upgrading to Path A injection-recovery as a methodology
  follow-up paper.

## What this design defers to v3

- Aperiodic / irregular-dimming search (Boyajian-class signals).
- Custom transit-search algorithms beyond what SPOC provides.

These require their own ingest pipeline (FFI light curves rather than
TCE XML); the v1 architecture intentionally does not constrain that
future design.
