# =============================================================================
# Ingest rules (Subsystem A)
# =============================================================================

rule build_parent_sample:
    """A1: Construct the frozen parent stellar sample."""
    input:
        config = "configs/parent_sample_v1.yaml",
        # TODO: also depend on Doyle+24 catalog file once paths are wired
    output:
        f"{PATHS['processed_data_dir']}/parent_sample_v1.parquet"
    log:
        f"{PATHS['log_dir']}/build_parent_sample.log"
    shell:
        # TODO: implement CLI entry point
        "python -m tess_megastructures.ingest.parent_sample "
        "--config {input.config} --output {output} 2> {log}"


rule download_sector_xml:
    """A2: Download all DV XML files for one sector run from MAST."""
    output:
        marker = touch(f"{PATHS['xml_dir']}/{{sector_run}}/.download_complete")
    log:
        f"{PATHS['log_dir']}/download_{{sector_run}}.log"
    threads: 8
    resources:
        mem_mb = 2000,
        runtime = 360  # minutes; downloads can be slow
    shell:
        "python -m tess_megastructures.ingest.download "
        "--sector-run {wildcards.sector_run} "
        "--output-dir {PATHS[xml_dir]}/{wildcards.sector_run} "
        "--max-concurrent {threads} 2> {log}"


rule parse_sector:
    """A3: Parse XML files for one sector run into a Parquet."""
    input:
        f"{PATHS['xml_dir']}/{{sector_run}}/.download_complete"
    output:
        f"{PATHS['processed_data_dir']}/tces_{{sector_run}}.parquet"
    log:
        f"{PATHS['log_dir']}/parse_{{sector_run}}.log"
    threads: 4
    resources:
        mem_mb = 8000,
        runtime = 60
    shell:
        "python -m tess_megastructures.ingest.parse "
        "--xml-dir {PATHS[xml_dir]}/{wildcards.sector_run} "
        "--output {output} "
        "--error-log {PATHS[log_dir]}/parse_errors_{wildcards.sector_run}.jsonl "
        "2> {log}"


rule concat_master_tces:
    """A5: Concatenate per-sector Parquets into the master TCE table."""
    input:
        expand(
            f"{PATHS['processed_data_dir']}/tces_{{sector_run}}.parquet",
            sector_run = ALL_SECTOR_RUNS
        )
    output:
        f"{PATHS['processed_data_dir']}/tces_master.parquet"
    log:
        f"{PATHS['log_dir']}/concat_master.log"
    shell:
        "python -m tess_megastructures.ingest.concat "
        "--inputs {input} --output {output} 2> {log}"
