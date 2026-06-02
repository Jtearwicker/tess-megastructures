# Design decisions log

A running log of non-obvious design decisions, with date and rationale.
Future-you (and future collaborators, and reviewers of the paper) will
appreciate this. Add entries; never remove them.

Format: dated entry with a one-line summary, the choice made, the
alternatives considered, and the reasoning.

When a later decision supersedes an earlier one, add a "Supersedes"
line to the new entry. Do NOT delete the older entry — the history
is the point.

---

## 2026-05-06 — v1 scope is candidates-only

**Choice:** v1 paper is the candidate catalog. v2 adds upper limits.
v3 adds aperiodic search.

**Alternatives considered:**

- Single-paper periodic-signals end-to-end (~18 months). Cleaner thesis
  chapter but no deliverable until end.
- Single-paper full Wright+16 menu (24+ months). Likely infeasible solo.

**Reasoning:** Staged papers give intermediate deliverables, build trust
in the filtering before claiming statistical results, and the v1 catalog
is independently citable. See architecture.md.

**Superseded by:** 2026-05-13 — v1 scope changed to upper limits.

---

## 2026-05-06 — Snakemake for orchestration

**Choice:** Snakemake.

**Alternatives considered:** Nextflow, Makefile + Python wrapper, raw shell scripts.

**Reasoning:** Standard in astronomy. Native cluster (SLURM) support.
Dependency model fits the per-sector parallelism + later injection-
recovery DAG. Worth the ~1 week learning cost given multi-year project.

---

## 2026-05-06 — Boolean filter columns instead of row deletion

**Choice:** Stage B annotates every TCE with `failed_*` boolean columns
and never drops rows. Candidate selection (C1) is a separate query.

**Alternatives considered:** Inherit predecessor's filter-and-reassign
pattern.

**Reasoning:** v2 detection-efficiency calculations need access to the
rejected sample. Filter tuning becomes a one-line config change rather
than re-parsing. See architecture.md.

---

## 2026-05-06 — Frozen parent sample versioning

**Choice:** `parent_sample_v1.parquet` is built once and never modified.
If cuts need to change, bump to `parent_sample_v2.parquet`.

**Reasoning:** The parent sample is the v2 occurrence-rate denominator.
Any silent change invalidates downstream statistical claims.

---

## 2026-05-06 — Streamlit for vetting interface

**Choice:** Streamlit, with a SQLite backing store.

**Alternatives considered:** Jupyter widgets (less polished UX),
static HTML reports (no fast classification UX), Google Sheets
(no rich rendering).

**Reasoning:** Vetting throughput is the v1 bottleneck; UX matters.
Streamlit is ~200 lines for a useful interactive app. Backing
store is shared with future Flask web service if vetting is ever
distributed to collaborators (no schema migration needed).

---

## 2026-05-06 — uv for environment management

**Choice:** uv.

**Alternatives considered:** conda/mamba (matches predecessor's
`environment.yml`), pip + venv.

**Reasoning:** uv is the modern fast option, lock files are reproducible,
single-tool workflow. The cluster may not have uv pre-installed; document
the install step in README.

---

## 2026-05-13 — v1 scope changed to upper limits

**Choice:** v1 paper now produces upper limits on megastructure
occurrence rate, not just a candidate catalog. The candidate catalog
becomes a byproduct.

**Alternatives considered:**

- Keep v1 as candidates-only, defer upper limits to v2 (original plan).
- Push for full Wright+16 menu with rigorous Path A in v1 (rejected as
  not feasible in a reasonable timeline).

**Reasoning:** Discussed with advisor. Their preference is to lead with
the statistical claim rather than the descriptive catalog. The
infrastructure built for v1 candidates (subsystems A/B/C) is correct
for both framings — what changes is that injection-recovery (subsystem
D and the inject module) moves from "v2 parallel work" into v1 scope.

**Supersedes:** 2026-05-06 — v1 scope is candidates-only.

**Implications:**

- Injection-recovery becomes phase 2 of v1 work, not v2.
- Vetting bar is higher: every survivor counts in the *k* for the
  Poisson upper limit calculation. False positives in the candidate
  set weaken the headline number.
- Parent sample becomes load-bearing — it's the denominator.
- Timeline is no longer ~9 months. Best honest estimate is 12–18+
  months for a defensible upper-limits result. Re-evaluate at month 4
  once we have throughput data. **TODO:** confirm timeline expectation
  with advisor in writing.

---

## 2026-05-13 — Four Wright+16 signal classes for v1

**Choice:** v1 covers three to four core Wright+16 periodic transit
signature classes: (1) standard transits at anomalous parameters,
(2) depth-varying transits, (3) asymmetric/non-circular transits,
(4) one additional class TBD (likely anomalous depth-duration ratio
or very long duration).

**Alternatives considered:**

- One signal class only (standard transits with anomalous parameters).
  Tractable but the megastructure framing demands broader coverage.
- Full Wright+16 menu including aperiodic. Multi-year effort, deferred
  to v3.

**Reasoning:** A megastructure-framed paper needs broader coverage than
"weird-looking transits" to be defensible. Three or four classes is
roughly the minimum to credibly claim "we searched for megastructures,"
while still being feasible solo. Architect the signal-model registry so
additional classes are drop-in additions.

---

## 2026-05-13 — Single combined upper-limit as headline result

**Choice:** v1 paper's headline statistic is a single upper limit on
megastructure occurrence rate, marginalized over the four signal
classes. Per-class efficiency tables and per-parameter sensitivity
maps live in the paper but are not the headline number.

**Alternatives considered:**

- Per-class limits as the headline (more informative, harder to
  summarize in an abstract).
- Both per-class and combined limits (more work; v1 keeps it simple,
  v2 or later paper can elaborate).

**Reasoning:** A single combined number is what reviewers and the
community will quote and cite. Per-class detail is in the paper for
those who want it. The marginalization requires prior weights on
signal classes; v1 uses uniform priors with the sensitivity to that
choice documented.

---

## 2026-05-13 — Detection efficiency via Path B (MES proxy) with serious calibration

**Choice:** Injection-recovery computes detection efficiency via a
documented MES (Multiple Event Statistic) proxy rather than a full
replica of SPOC's TPS+DV pipeline. A calibration appendix is treated
as a first-class methodological contribution.

**Alternatives considered:**

- Path A: replicate SPOC's full transit-search and DV pipeline.
  Rigorous but 6-12+ months of additional work to develop and
  validate. Probably the right choice for a follow-up paper.
- Hybrid: Path B for the bulk, Path A on a validation subset. May
  evolve in this direction during v1 if Path B's systematics turn
  out to be larger than expected.

**Reasoning:** A well-calibrated proxy with bounded systematic error
is defensible as long as the systematic uncertainty on η is smaller
than the statistical uncertainty on the limit. The calibration plan:

1. Compute MES proxy for every real SPOC TCE in our parsed table.
2. Compare proxy MES to SPOC's reported MES. Residual distribution
   characterizes the proxy's systematic error.
3. Forward-validate by injecting synthetic signals into FFI light
   curves and confirming recovery rates match expectations.
4. Sensitivity-analyze the upper limit under 10%, 20%, 50% miscalibration
   assumptions.

If a 20% MES miscalibration moves the headline limit by less than its
statistical uncertainty, the proxy is good enough.

---

## 2026-05-13 — Parser output schema: snake_case columns, nullable dtypes

**Choice:** Output Parquet columns use snake_case names (`model_chi_square`,
not `modelChiSquare`). Missing optional fields are stored as None (which
becomes pandas null / Parquet null) rather than sentinel values like NaN
or -1.

**Alternatives considered:**

- camelCase matching SPOC's XML attribute names. Pro: no translation
  layer when consulting SPOC documentation.
- NaN/sentinel values for missing fields. Pro: simpler in pure-pandas
  queries that don't handle null.

**Reasoning:** Python convention is snake_case; queries downstream
read more naturally (`tces.query("failed_ghost == False")`). The
translation between SPOC's camelCase names and our snake_case columns
is small (a comment in each extraction function noting the source
attribute). Nullable dtypes preserve the distinction between "value
was zero/false" and "value was missing," which matters for downstream
filtering.

---

## 2026-05-13 — Decode sectorsObserved bitmask into a list of sector ints

**Choice:** The parser decodes SPOC's `sectorsObserved` bitmask string
into a list of sector ints (e.g., `[36, 37, 38]`), stored as a column
alongside the raw bitmask string.

**Reasoning:** Downstream code (parent sample, sector-aware injection)
needs to know which sectors observed each TIC. The raw bitmask is kept
for traceability; the decoded list is what consumers actually use.

---

## 2026-05-13 — Parser uses namespace-aware lookup, not positional indexing

**Choice:** The new parser uses `element.find("{ns}tag")` and similar
named-element lookups throughout. The predecessor's parser used
positional indexing in the centroid extraction (`e0[0][2]`), which
was the most dangerous bug in the inherited code.

**Reasoning:** Named-element lookup is robust to SPOC schema reorderings.
Positional indexing produces silent wrong values if SPOC ever adds or
reorders sibling elements. The positional approach happened to work
for the current schema but is a time bomb.

---

## 2026-05-13 — Drop `modelParameterCovariance` from parsed output

**Choice:** The parser does not extract the full model parameter
covariance matrix (which is hundreds of floats per TCE in the XML).

**Reasoning:** No downstream code in v1 or v2 uses the covariance
matrix. Including it bloats the Parquet substantially. Re-add if a
future analysis needs it; it's still in the source XML.

---

## 2026-05-19 — Reverted: v1 back to candidates catalog (not upper limits)

**Choice:** v1 is once again a candidate catalog, NOT an upper-limits
paper. Upper limits return to v2/future.

**Reasoning:** The 2026-05-13 switch to upper-limits-in-v1 was
re-examined against the timeline. A defensible upper limit requires the
full injection-recovery + detection-efficiency apparatus (12-18+ months
solo), which did not fit the ~9-month expectation. Rather than compromise
rigor, v1 reverts to the candidate-catalog deliverable, which is
publishable, citable, and sets up v2 upper limits from a stronger
position (v1's vetted catalog becomes v2's validation input).

**Supersedes:** 2026-05-13 — v1 scope changed to upper limits.

**Implications:**

- Injection-recovery, MES proxy, and the inject/infer subsystems return
  to v2 scope. Not built for v1.
- The "four Wright+16 signal classes" and "single combined upper limit"
  decisions (both 2026-05-13) are scoped to v2; they describe the
  upper-limits framing, not the v1 candidate catalog.
- Vetting bar returns to candidate-catalog level (defensible
  classifications) rather than the stricter every-survivor-counts bar
  that upper limits demand.

---

## 2026-05-20 — v1 adopts the MegaMiner ML pipeline (plan of record)

**Choice:** v1 is the MegaMiner pipeline: an ML-driven candidate search
over the full SPOC FFI TCE population (~1M TCEs across all FFI sectors),
narrowing to a vetted anomaly/candidate catalog framed around
megastructure signatures. Pipeline stages:

  TCEs -> manual cuts -> ExoMiner score + EB/Z score
       -> autoencoder anomaly detector -> LLM-based triage
       -> (agentic orchestration) -> vetted candidates

**Alternatives considered:**

- The prior hand-built candidate pipeline (manual filters + human
  vetting only). Superseded by the ML approach, which scales to ~1M TCEs.
- Building all ML components in-house. Rejected: several components are
  external/collaborator-provided (see below).

**Reasoning:** Advisor's direction. The ML pipeline scales the candidate
search far beyond what manual filtering + human vetting could cover, and
brings in established tools (ExoMiner) plus collaborator ML expertise.
The headline v1 deliverable remains a candidate catalog (Definition B
TCE population in, vetted candidates out) — upper limits stay in v2.

**Supersedes:** the candidate-pipeline framing in 2026-05-19 (same
deliverable — a candidate catalog — but a different, ML-driven method).

**Component ownership (as currently understood):**

- **Manual cuts / filtering:** this project (builds on the parser +
  annotation work). Ours.
- **ExoMiner scoring:** external published tool (NASA). Integration, not
  novel ML. Note: ExoMiner++ 2.0 (Jan 2026, arXiv 2601.14877) vets FFI
  TCEs specifically; an FFI score catalog may already exist — TODO check
  before building integration.
- **Autoencoder anomaly detector:** provided by NASA Ames collaborators
  (imported, NOT built from scratch here).
- **LLM-based triage:** scope TBD; intended use is literature
  cross-referencing / candidate summarization / human-in-the-loop
  triage, NOT an autonomous final classifier.
- **Agentic orchestration:** deferred. NemoClaw (Nvidia) was floated as
  one option; no agent is committed. Cannot orchestrate a pipeline that
  does not yet exist — this is a last layer, not a foundation.

**TODOs (unresolved details within the committed MegaMiner plan):**

- Confirm this project's specific first-author contribution within the
  multi-person effort (collaborators: iangelo/Isabel Angelo
  [predecessor], vishalg). Likely core: filtering + science framing +
  signal taxonomy + known-anomaly validation set + candidate vetting.
- Confirm timeline.
- Resolve which agentic-orchestration tool, if any, and whether it is in
  v1 at all.

---

## 2026-05-20 — v1 sample is the TCE population (Definition B), not the stellar parent sample (Definition A)

**Choice:** The v1 "sample" is the TCE population: every SPOC FFI TCE,
aggregated across sectors (Definition B). The stellar occurrence-rate
denominator (all searched stars including non-detections; Definition A)
is deferred to v2.

**Alternatives considered:**

- Definition A (all searched FFI targets, ~160k/sector). The correct
  denominator for an occurrence-rate/upper-limit claim, but v1 makes no
  such claim, and A requires a separate large MAST target-list query.
- Build both now. Over-building for a v1 that does not need A.

**Reasoning:** v1 (MegaMiner candidate catalog) operates ON TCEs and
makes a candidate claim, not a rate claim. The relevant population is
therefore the TCE population (B), which also reuses parser output rather
than requiring a new query. A is a v2 concern (upper limits). The module
is structured so A can be added later as an additive change.

**Naming consequence:** the Definition-B artifact is named
`tce_sample_v1.parquet` / `tce_sample.py`, NOT "parent sample." The term
"parent sample" is reserved for the Definition-A stellar denominator
(the existing `parent_sample.py` stub) when v2 needs it. Calling a
TCE-level table a "parent sample" would mislead, since the term has a
specific occurrence-rate meaning.

---

## 2026-05-20 — TCE sample module design (Definition B)

**Choice:** `tce_sample.py` builds the Definition-B sample with:

- One row per `(tic_id, planet_number, sector)` — fully granular;
  multi-sector detections of the same signal are separate rows.
- A `run_type` column ("single_sector"/"multi_sector"), derived from the
  parser's `n_difference_images`.
- DV-extracted stellar params as PRIMARY (complete coverage from the
  parser); Doyle+24 Gaia params as an ENRICHMENT layer (`doyle_` prefix,
  flagged by `has_doyle_params`), attached only where the cross-match
  hits.
- Configurable boolean cuts (tmag, log_g, parallax SNR, RUWE) with
  PLACEHOLDER values; `in_clean_sample` is the AND of the cuts listed in
  `required_for_clean`. Rows are never dropped.

**Reasoning:** Granularity is reversible (collapse later) but loss is
not. DV-params-primary sidesteps Doyle+24 coverage gaps. Cut VALUES are a
science decision deferred to later; the module reads them from
`tce_sample_v1.yaml` so finalizing them is a one-line edit, no code
change. Mirrors the parser's conventions (snake_case, nullable,
never-drop-rows).

---

## 2026-05-20 — Validate locally before running on the node

**Choice:** Standing workflow: develop and test on a local machine
(pytest + ruff green) -> push -> CI green (3.11/3.12) -> only then
`git pull` on tarang-node1. The node receives only code already
validated elsewhere; CI is the authoritative gate before the node.

**Reasoning:** Keeps the cluster as an execution environment, not a
debugging environment. Local machines run newer Python (3.13/3.14) than
the node (3.12) and CI (3.11/3.12), so CI — not local green — is the
authoritative cross-version check. Heavy scale runs (full-sector parse,
ExoMiner, etc.) happen on the node only after small-input validation.

---

## 2026-05-28 — Diagnostic vetting as flags, not cuts

**Choice:** Reimplement Isabel's `create_tce_batches.py` vetting chain as
boolean `flag_*` columns on the TCE sample (True = suspicious), never
dropping rows. Candidate selection is a query over the flags rather than a
destructive batch-priority filter. Thresholds live in config.

**Alternatives considered:** (1) Reproduce the original hard-cut batch
chain that removes rows at each stage. (2) Skip classical filtering
entirely and rely on the ML stages (ExoMiner, autoencoder) for
false-positive rejection.

**Reasoning:** Flags preserve information that hard cuts destroy — for an
anomaly search, today's "junk" filter could discard tomorrow's interesting
object. Flagging also defers the contentious threshold decisions (the
inherited magic numbers) to a single tunable query step, and complements
rather than competes with the ML scores. Consistent with the existing
never-drop-rows principle already used for the stellar cuts.

**Supersedes:** Extends the never-drop-rows decision to the full diagnostic
layer.

---

## 2026-05-28 — Doyle+24 is a stellar-parameter source, not an EB catalog

**Choice:** Use Doyle+24 only for stellar parameters and astrometric
binarity indicators (RUWE, parallax SNR). Use dedicated eclipsing-binary
catalogs (Prsa+22, Kostov+25) for actual EB identification.

**Alternatives considered:** Treating Doyle's RUWE / non-single-star flags
as an EB catalog (the implicit prior usage that prompted a team concern
that Doyle "includes non-EBs and misses known EBs").

**Reasoning:** Doyle+24 is a Gaia-based characterization of the full
SPOC FFI target sample, not an EB catalog. RUWE > 1.4 is a soft astrometric
binarity hint, not an EB confirmation — so the sample necessarily includes
non-EBs (most targets) and misses EBs with clean astrometry. The concern is
real but points at a usage error, not a defect. Doyle stays for params; EB
identification moves to purpose-built catalogs.

---

## 2026-05-28 — TIC stellar-parameter sentinel value

**Choice:** Treat the value combination Teff = 31000 K, log g = 5.59962,
radius = 0.18 R_sun as a sentinel for "no real stellar characterization,"
to be flagged (future Subsystem B annotation) rather than trusted.

**Alternatives considered:** Treating these as real stellar parameters.

**Reasoning:** Discovered in the first s0055 end-to-end run: three distinct
TICs (different magnitudes) carried bit-identical Teff/log g/radius to many
decimal places. The combination is physically impossible (31000 K is an
O-type star; 0.18 R_sun is an M dwarf), so it is a placeholder the TIC
emits when parameters are unknown. ~0.1% of TCEs (3 / 2795) in s0055. It
passes the `log_g >= 3.5` cut by coincidence, so existing cuts do not catch
it; a dedicated `has_sentinel_stellar_params` flag is the right fix when
catalog/annotation work resumes.

---

## 2026-05-28 — Deep-eclipse EBs are the dominant survivor contaminant

**Choice:** Record (for the catalog-cross-match design) that symmetric,
on-target, deep eclipsing binaries pass the current diagnostic chain and
dominate the unflagged survivor set. Plan to address via EB-catalog
cross-match (Prsa, Kostov) and consider a depth-based flag.

**Alternatives considered:** Assuming the current diagnostics already remove
EBs adequately.

**Reasoning:** The first s0055 run produced 43 unflagged TCEs; a large
fraction had transit depths of 10–30%, which are eclipsing binaries (planets
cap near 1–2%). They survive because the existing tests catch asymmetric or
blended EBs (odd/even, ghost, centroid) but not clean, symmetric, on-target
deep eclipses. This motivates the catalog cross-match as the next build and
a possible `flag_deep_eclipse`. (The depth flag is a proposed addition to
Isabel's chain, pending team input.)


## TEMPLATE for future entries

## YYYY-MM-DD — Short summary

**Choice:** What was decided.

**Alternatives considered:** What else was on the table.

**Reasoning:** Why this option, with any trade-offs noted.

**Supersedes:** (Optional) Reference to an earlier entry this replaces.
