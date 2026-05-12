# Design decisions log

A running log of non-obvious design decisions, with date and rationale.
Future-you (and future collaborators, and reviewers of the paper) will
appreciate this. Add entries; never remove them.

Format: dated entry with a one-line summary, the choice made, the
alternatives considered, and the reasoning.

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

## TEMPLATE for future entries

## YYYY-MM-DD — Short summary

**Choice:** What was decided.

**Alternatives considered:** What else was on the table.

**Reasoning:** Why this option, with any trade-offs noted.
