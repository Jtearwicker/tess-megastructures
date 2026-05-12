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
2. **Annotates** every TCE with derived metrics, catalog cross-matches,
   filter flags, and an anomaly score — without discarding rows.
3. **Vets** the surviving candidates via a structured human-review interface.
4. **(Future)** Computes detection efficiency via injection-recovery and
   sets upper limits on megastructure occurrence rates.

The architecture is documented in [`docs/architecture.md`](docs/architecture.md).

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
uv sync --extra all     # Install all dependencies (vet + workflow + dev)
```

For library use only (no Streamlit, no Snakemake):

```bash
uv sync                 # Just core dependencies
```

### Configure paths

Per-machine paths live in `configs/paths.yaml`, which is gitignored. Copy the
template and edit:

```bash
cp configs/paths.example.yaml configs/paths.yaml
$EDITOR configs/paths.yaml
```

### Run tests

```bash
uv run pytest
```

### Run the pipeline

The pipeline is orchestrated with Snakemake.

```bash
# Local execution, single sector
uv run snakemake --profile workflow/profiles/local --cores 4 ingest_sector_s0055

# Cluster execution (SLURM), all sectors
uv run snakemake --profile workflow/profiles/cluster all
```

See `docs/per_subsystem/` for what each stage does.

## Repository layout

```
src/tess_megastructures/    Library code (subsystems A–D, catalog loaders)
apps/vetting_app/           Streamlit interface for human candidate review
configs/                    Versioned YAML configs (filter thresholds, etc.)
workflow/                   Snakemake rules and execution profiles
tests/                      Unit + integration tests
docs/                       Architecture, per-subsystem docs, decision log
```

See `docs/architecture.md` for the full design rationale.

## Citing

When this is published, citation info will go here.

## License

MIT — see [LICENSE](LICENSE).
