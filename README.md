# tess-megastructures

A pipeline for identifying anomalous transit signals in TESS-SPOC Data Validation
products and setting upper limits on the prevalence of megastructures (Wright+16)
in the TESS-observed stellar sample.

## Status

Pre-alpha. The pipeline is under active development and APIs will change.

## What this is

This repository builds on TESS Science Processing Operations Center (SPOC)
Data Validation reports for full-frame-image targets (Caldwell+20). It:

1. **Ingests** TCE metadata from per-sector DV XML reports.
2. **Annotates** every TCE with derived metrics and diagnostic filter flags
   — without discarding rows.
3. **Vets** the surviving candidates (human/LLM review — in progress).
4. **(Future)** Computes detection efficiency via injection-recovery and
   sets upper limits on megastructure occurrence rates.

The architecture is documented in [`docs/architecture.md`](docs/architecture.md),
and each subsystem in [`docs/per_subsystem/`](docs/per_subsystem/).

## Project staging

This is a multi-paper effort:

- **v1 — Anomaly catalog (~9 months):** vetted catalog of TCEs that
  don't fit standard astrophysical explanations.
- **v2 — Upper limits (~18 months):** occurrence rate constraints on
  periodic transit signatures, via injection-recovery.
- **v3 — Aperiodic search (post-v2):** custom light-curve searches for
  Boyajian-style irregular dimming.

The current codebase targets v1.

## Quickstart

### Install

The project uses [uv](https://docs.astral.sh/uv/) for environment management.

```bash
# Install uv if you don't already have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone <repo-url>
cd tess-megastructures
uv sync                 # core dependencies
uv sync --extra vet     # add the vetting-app deps (streamlit, matplotlib, lightkurve)
```

### Configure paths

Per-machine paths live in `configs/paths.yaml`, which is gitignored. Copy the
template and edit:

```bash
cp configs/paths.example.yaml configs/paths.yaml
$EDITOR configs/paths.yaml
```

The keys used by the pipeline:

- `xml_dir` — directory of downloaded per-sector DV XML reports
- `processed_data_dir` — where parsed per-sector Parquets are written
- `output_dir` — where the built TCE sample and dashboard are written
- `doyle2024_catalog` — path to the Doyle+24 main-sequence catalog file

### Run tests

```bash
uv run pytest
```

## Running the pipeline

The pipeline runs as a sequence of direct scripts. (A Snakemake workflow
exists under `workflow/` but is not the maintained path; use the scripts
below.) Each step reads paths from `configs/paths.yaml`.

### 1. Parse a sector's DV reports into a TCE table

Downloads/locates the per-sector DV XML files and parses them into a
per-sector Parquet of TCE metrics.

```bash
uv run python -m tess_megastructures.ingest.parse \
    --xml-dir   /path/to/sector/xml \
    --output    /path/to/processed/tce_dv_metrics_s0067.parquet \
    --error-log /path/to/processed/parse_errors_s0067.log
```

One row per TCE; ~70 columns of DV metrics. See
[`docs/data_dictionary.md`](docs/data_dictionary.md) for the schema. The
parser exits nonzero only if *every* file fails; per-file failures are
recorded in the error log and skipped.

### 2. Build the TCE sample

Aggregates all parsed sector Parquets found in `processed_data_dir`, enriches
with Doyle+24 stellar parameters, applies the stellar selection cuts, and adds
the Subsystem-B diagnostic flags (derived metrics + boolean `flag_*` columns,
True = suspicious; no rows are dropped). Writes `tce_sample_v1.parquet` to
`output_dir` and prints a summary including per-flag counts.

```bash
uv run python scripts/build_tce_sample.py
```

Thresholds for the stellar cuts and diagnostic flags live in
`configs/tce_sample_v1.yaml`. See
[`docs/per_subsystem/B_annotate.md`](docs/per_subsystem/B_annotate.md).

### 3. Inspect the result

Generate a standalone HTML report (funnel, per-flag breakdown, distributions,
flag co-occurrence, and the unflagged-survivor table):

```bash
uv run python scripts/make_dashboard.py /path/to/output/tce_sample_v1.parquet
# writes tce_sample_v1_dashboard.html next to the input
```

It is a self-contained file (no external dependencies). If the sample was
built on a remote node, copy the HTML to your machine to view it.

## Development workflow

Code is developed and tested locally, then run on the compute node:

1. Develop + test locally: `uv run ruff format <files>`, `uv run ruff check .`,
   `uv run ruff format --check .`, `uv run pytest`.
2. Push; CI runs the test suite on Python 3.11 and 3.12 (the authoritative
   cross-version gate).
3. Once CI is green, `git pull` on the node and run the heavy steps
   (parsing, sample build) there.

See [`docs/decisions.md`](docs/decisions.md) for the rationale (validate
locally, the node is an execution environment not a debugging one).

## Repository layout

```
src/tess_megastructures/    Library code (subsystems A–D, catalog loaders)
  ingest/                   Parser + TCE-sample build (Subsystem A)
  annotate/                 Derived metrics + diagnostic flags (Subsystem B)
  catalogs/                 Catalog loaders (Doyle+24 implemented; others stubbed)
  vet/                      Candidate review (Subsystem C — in progress)
apps/vetting_app/           Streamlit interface for human candidate review
scripts/                    Pipeline runners (build_tce_sample, make_dashboard)
configs/                    Versioned YAML configs (cut + flag thresholds)
workflow/                   Snakemake rules (not the maintained run path)
tests/                      Unit + integration tests
docs/                       Architecture, per-subsystem docs, data dictionary, decisions
```

## Citing

When this is published, citation info will go here.

## License

MIT — see [LICENSE](LICENSE).
