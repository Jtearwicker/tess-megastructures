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

## TEMPLATE for future entries

## YYYY-MM-DD — Short summary

**Choice:** What was decided.

**Alternatives considered:** What else was on the table.

**Reasoning:** Why this option, with any trade-offs noted.

**Supersedes:** (Optional) Reference to an earlier entry this replaces.
