# =============================================================================
# Annotation rules (Subsystem B)
# =============================================================================

rule simbad_xmatch:
    """B4: Query SIMBAD for all TICs in the master sample, with caching."""
    input:
        tces = f"{PATHS['processed_data_dir']}/tces_master.parquet",
        types_config = "configs/simbad_types.yaml"
    output:
        f"{PATHS['processed_data_dir']}/simbad_results.parquet"
    log:
        f"{PATHS['log_dir']}/simbad_xmatch.log"
    resources:
        mem_mb = 4000,
        runtime = 120,
        # SIMBAD throttles; only run one job at a time.
        simbad_slots = 1
    shell:
        "python -m tess_megastructures.annotate.simbad_xmatch "
        "--tces {input.tces} "
        "--cache-dir {PATHS[simbad_cache_dir]} "
        "--types-config {input.types_config} "
        "--output {output} 2> {log}"


rule annotate_tces:
    """B1-B6: Add derived metrics, harmonic flags, catalog flags,
    SIMBAD flags, filter columns, and anomaly score."""
    input:
        tces = f"{PATHS['processed_data_dir']}/tces_master.parquet",
        parent = f"{PATHS['processed_data_dir']}/parent_sample_v1.parquet",
        simbad = f"{PATHS['processed_data_dir']}/simbad_results.parquet",
        filter_config = "configs/filter_config_v1.yaml",
        score_config = "configs/score_config_v1.yaml",
        catalogs_config = "configs/catalogs.yaml"
    output:
        f"{PATHS['processed_data_dir']}/tces_annotated_v1.parquet"
    log:
        f"{PATHS['log_dir']}/annotate.log"
    resources:
        mem_mb = 16000,
        runtime = 30
    shell:
        "python -m tess_megastructures.annotate "
        "--tces {input.tces} "
        "--parent {input.parent} "
        "--simbad {input.simbad} "
        "--filter-config {input.filter_config} "
        "--score-config {input.score_config} "
        "--catalogs-config {input.catalogs_config} "
        "--output {output} 2> {log}"
