# Data dictionary

Column-by-column reference for every output Parquet file. Filled in as
each subsystem is implemented. Definitions here are normative — code
that adds columns must also update this file.

## `parent_sample_v1.parquet` (Subsystem A1)

One row per TIC.

| Column | Type | Source | Definition |
|---|---|---|---|
| `ticId` | int64 | TIC catalog | TESS Input Catalog identifier |
| `ra_deg` | float64 | TIC | RA in degrees, ICRS |
| `dec_deg` | float64 | TIC | Dec in degrees, ICRS |
| `sectors_observed` | list[int] | SPOC FFI target lists | Sectors in which TIC was processed |
| `total_baseline_days` | float64 | derived | Sum of unique sector durations |
| `effective_temp` | float64 | Doyle+24 | Stellar Teff (K) |
| `radius` | float64 | Doyle+24 | Stellar radius (R_sun) |
| `log_g` | float64 | Doyle+24 | log surface gravity |
| `tess_mag` | float64 | TIC | T magnitude |
| `parallax` | float64 | Doyle+24 | Gaia parallax (mas) |
| `parallax_over_error` | float64 | Doyle+24 | Gaia parallax SNR |
| `ruwe` | float64 | Doyle+24 | Gaia RUWE |
| `passed_brightness_cut` | bool | derived | Tmag in config range |
| `passed_parallax_cut` | bool | derived | parallax_over_error >= threshold |
| `passed_log_g_cut` | bool | derived | log_g >= threshold (MS) |
| `has_valid_stellar_params` | bool | derived | All required params non-NaN |
| `in_clean_sample` | bool | derived | AND of all required cuts |
| `low_ruwe` | bool | derived | RUWE < threshold (single-star clean cut) |

## `tces_master.parquet` (Subsystem A5)

One row per TCE.

TODO: Document after parser refactor. Schema must be stable.

## `tces_annotated_v1.parquet` (Subsystem B7)

One row per TCE. Same row count and primary key as `tces_master.parquet`.

TODO: Document after annotation modules are implemented.

## `vetting_queue.parquet` (Subsystem C1)

Subset of `tces_annotated_v1.parquet` selected for human review.

TODO: Document after candidate selection is implemented.

## `vetting_log.sqlite` (Subsystem C5)

Schema documented in `src/tess_megastructures/vet/log.py`.
