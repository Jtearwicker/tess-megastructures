# =============================================================================
# Vetting rules (Subsystem C)
# =============================================================================
# Note: the actual human vetting happens via the Streamlit app and is not
# a Snakemake rule. These rules build the queue and the per-candidate
# packages, then humans take over.

rule build_vetting_queue:
    """C1: Select candidates from the annotated table."""
    input:
        annotated = f"{PATHS['processed_data_dir']}/tces_annotated_v1.parquet"
    output:
        f"{PATHS['output_dir']}/vetting_queue_v1.parquet"
    log:
        f"{PATHS['log_dir']}/build_queue.log"
    shell:
        "python -m tess_megastructures.vet.candidates "
        "--annotated {input.annotated} "
        "--output {output} 2> {log}"


rule generate_vetting_packages:
    """C2: Build per-candidate review packages for the entire queue."""
    input:
        queue = f"{PATHS['output_dir']}/vetting_queue_v1.parquet"
    output:
        # Marker file so Snakemake can track completion.
        marker = touch(f"{PATHS['vetting_packages_dir']}/.packages_built")
    log:
        f"{PATHS['log_dir']}/generate_packages.log"
    threads: 4
    resources:
        mem_mb = 8000,
        runtime = 240
    shell:
        "python -m tess_megastructures.vet.packages "
        "--queue {input.queue} "
        "--output-dir {PATHS[vetting_packages_dir]} 2> {log}"


# Convenience target that builds everything needed to start vetting.
rule ready_for_vetting:
    input:
        f"{PATHS['output_dir']}/vetting_queue_v1.parquet",
        f"{PATHS['vetting_packages_dir']}/.packages_built"
