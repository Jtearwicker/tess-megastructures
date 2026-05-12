# =============================================================================
# tess-megastructures Snakefile
# =============================================================================
# Top-level pipeline DAG. Concrete rules live in workflow/rules/.
#
# Common invocations:
#
#   # Local development (single sector)
#   snakemake --profile workflow/profiles/local --cores 4 ingest_one_sector
#
#   # Cluster (SLURM) — all sectors
#   snakemake --profile workflow/profiles/cluster all
#
#   # Just rebuild the candidate queue from existing annotated table
#   snakemake --profile workflow/profiles/local vetting_queue
#
# See README.md for full instructions.
# =============================================================================

import yaml
from pathlib import Path

# -----------------------------------------------------------------------------
# Load per-machine paths
# -----------------------------------------------------------------------------
# paths.yaml is gitignored and machine-specific. Falls back to the example
# template (with a warning) for CI / smoke testing.
_paths_file = Path("configs/paths.yaml")
if not _paths_file.exists():
    _paths_file = Path("configs/paths.example.yaml")
    print(
        f"WARNING: configs/paths.yaml not found, using {_paths_file} as fallback. "
        "Real runs require a per-machine paths.yaml."
    )

with open(_paths_file) as f:
    PATHS = yaml.safe_load(f)

# -----------------------------------------------------------------------------
# Sector inventory
# -----------------------------------------------------------------------------
with open("configs/parent_sample_v1.yaml") as f:
    _parent_cfg = yaml.safe_load(f)

SINGLE_SECTORS = [f"s{n:04d}" for n in _parent_cfg["sectors"]["single_sector_runs"]]
MULTI_SECTOR_RUNS = _parent_cfg["sectors"]["multi_sector_runs"]
ALL_SECTOR_RUNS = SINGLE_SECTORS + MULTI_SECTOR_RUNS

# -----------------------------------------------------------------------------
# Include rule files
# -----------------------------------------------------------------------------
include: "workflow/rules/ingest.smk"
include: "workflow/rules/annotate.smk"
include: "workflow/rules/vet.smk"

# -----------------------------------------------------------------------------
# Top-level targets
# -----------------------------------------------------------------------------

rule all:
    """Build the full v1 vetting queue from raw XML to candidate list."""
    input:
        f"{PATHS['output_dir']}/vetting_queue_v1.parquet"


rule ingest_all:
    """Download and parse all sectors. Stops before annotation."""
    input:
        f"{PATHS['processed_data_dir']}/tces_master.parquet"


rule ingest_one_sector:
    """Convenience target: ingest a single sector. Override SECTOR=...
    at the command line."""
    input:
        f"{PATHS['processed_data_dir']}/tces_{{sector_run}}.parquet"


# Default sector for `ingest_one_sector` if SECTOR is not set.
wildcard_constraints:
    sector_run = r"s\d{4}(-s\d{4})?"
