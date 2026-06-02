# Data dictionary

Column-by-column reference for every output Parquet file. Filled in as
each subsystem is implemented. Definitions here are normative — code
that adds columns must also update this file.

When a schema changes intentionally, update this file in the same commit
as the code change. The parser's smoke test (`tests/test_parse.py`)
enforces this for `tce_dv_metrics_*.parquet` by comparing against a
committed expected-output fixture.

---

## `tce_dv_metrics_<sector>.parquet` (Subsystem A3 — parser output)

One row per TCE (per `planetResults` element). Target-level fields
(TIC, stellar properties, limb darkening) are duplicated across all
TCEs from the same target. Produced by
`src/tess_megastructures/ingest/parse.py`. 68 columns.

Column naming is snake_case; missing optional fields are null (not a
sentinel value). See decisions.md (2026-05-13, parser schema entry).

### Target-level columns

| Column | Type | Source (XML) | Definition |
|---|---|---|---|
| `tic_id` | int64 | `dvTargetResults@ticId` | TESS Input Catalog identifier |
| `toi_id` | string | `dvTargetResults@toiId` | TOI identifier if assigned, else null |
| `matched_toi_ids` | list[string] | `matchedToiId` elements | All matched TOI IDs |
| `planet_candidate_count` | int32 | `@planetCandidateCount` | Number of TCEs for this target |
| `sectors_observed_bitmask` | string | `@sectorsObserved` | Raw 64-bit observation bitmask |
| `sectors_observed` | list[int] | derived | Decoded list of observed sector numbers |
| `start_cadence` | int64 | `@startCadence` | First cadence |
| `end_cadence` | int64 | `@endCadence` | Last cadence |
| `pipeline_task_id` | int64 | `@pipelineTaskId` | SPOC pipeline task id |
| `ra_deg` | float64 | `raDegrees@value` | RA, degrees |
| `dec_deg` | float64 | `decDegrees@value` | Dec, degrees |
| `pm_ra` | float64 | `pmRa@value` | Proper motion RA |
| `pm_dec` | float64 | `pmDec@value` | Proper motion Dec |
| `tess_mag` | float64 | `tessMag@value` | TESS magnitude |
| `effective_temp` | float64 | `effectiveTemp@value` | Stellar Teff (K) |
| `radius` | float64 | `radius@value` | Stellar radius (R_sun) |
| `log_g` | float64 | `log10SurfaceGravity@value` | log surface gravity |
| `log_metallicity` | float64 | `log10Metallicity@value` | log metallicity |
| `stellar_density` | float64 | `stellarDensity@value` | Stellar density |
| `limb_darkening_model` | string | `limbDarkeningModel@modelName` | LD model name |
| `limb_darkening_c1`..`c4` | float64 | `@coefficient1..4` | LD coefficients |

### Per-TCE columns

| Column | Type | Source (XML) | Definition |
|---|---|---|---|
| `planet_number` | int32 | `planetResults@planetNumber` | TCE index within target |
| `tce_toi_id` | string | `planetResults@toiId` | Per-TCE TOI id if any |
| `toi_correlation` | float64 | `@toiCorrelation` | Correlation with matched TOI |
| `detrend_filter_length` | int32 | `@detrendFilterLength` | Detrending filter length |

### planetCandidate sub-element

| Column | Type | Source | Definition |
|---|---|---|---|
| `suspected_eclipsing_binary` | bool | `planetCandidate@suspectedEclipsingBinary` | SPOC EB flag |
| `max_single_event_sigma` | float64 | `@maxSingleEventSigma` | Max single-event statistic |
| `max_multiple_event_sigma` | float64 | `@maxMultipleEventSigma` | MES |
| `robust_statistic` | float64 | `@robustStatistic` | Robust detection statistic |
| `model_chi_square_2` | float64 | `@modelChiSquare2` | Chi-square (model 2) |
| `model_chi_square_dof_2` | float64 | `@modelChiSquareDof2` | DOF (model 2) |
| `model_chi_square_gof` | float64 | `@modelChiSquareGof` | Goodness-of-fit chi-square |
| `model_chi_square_gof_dof` | float64 | `@modelChiSquareGofDof` | GOF DOF |

### allTransitsFit + model parameters

| Column | Type | Source | Definition |
|---|---|---|---|
| `full_convergence` | bool | `allTransitsFit@fullConvergence` | Fit converged |
| `model_chi_square` | float64 | `@modelChiSquare` | All-transits-fit chi-square |
| `model_degrees_of_freedom` | float64 | `@modelDegreesOfFreedom` | Fit DOF |
| `model_fit_snr` | float64 | `@modelFitSnr` | Fit S/N |
| `transit_model_name` | string | `@transitModelName` | Transit model used |
| `transit_epoch_btjd` (+`_err`) | float64 | modelParameter | Transit epoch (BTJD) |
| `min_impact_parameter` (+`_err`) | float64 | modelParameter | Impact parameter |
| `orbital_period_days` (+`_err`) | float64 | modelParameter | Orbital period (days) |
| `ratio_planet_radius_to_star_radius` (+`_err`) | float64 | modelParameter | Rp/R* |
| `ratio_semi_major_axis_to_star_radius` (+`_err`) | float64 | modelParameter | a/R* |
| `transit_duration_hours` (+`_err`) | float64 | modelParameter | Transit duration (hr) |
| `transit_depth_ppm` (+`_err`) | float64 | modelParameter | Transit depth (ppm) |

### Diagnostics (binary discrimination, bootstrap, centroid, ghost, difference image)

| Column | Type | Source | Definition |
|---|---|---|---|
| `odd_even_depth_statistic` | float64 | `oddEvenTransitDepthComparisonStatistic@value` | Odd/even depth comparison |
| `odd_even_depth_significance` | float64 | `@significance` | Its significance |
| `bootstrap_significance` | float64 | `bootstrapResults@significance` | Bootstrap false-alarm significance |
| `ms_tic_centroid_offset_sigma` | float64 | derived (named lookup) | TIC-position mean-sky-offset / uncertainty |
| `ms_control_centroid_offset_sigma` | float64 | derived (named lookup) | Control mean-sky-offset / uncertainty |
| `ghost_core_correlation` | float64 | `coreApertureCorrelationStatistic@value` | Ghost diagnostic core |
| `ghost_core_correlation_significance` | float64 | `@significance` | Its significance |
| `ghost_halo_correlation` | float64 | `haloApertureCorrelationStatistic@value` | Ghost diagnostic halo |
| `ghost_halo_correlation_significance` | float64 | `@significance` | Its significance |
| `sector` | int32 | `differenceImageResults@sector` (last) | Sector of last difference image |
| `n_difference_images` | int32 | derived (count) | Number of difference-image results (>1 means multi-sector) |

### Provenance columns (added by parser)

| Column | Type | Definition |
|---|---|---|
| `xml_filename` | string | Basename of source XML |
| `parser_version` | string | Package version at parse time |
| `parsed_at` | string | UTC ISO timestamp |

> Note: `modelParameterCovariance` is intentionally NOT extracted (large,
> unused downstream). See decisions.md (2026-05-13).

---

## `tce_sample_v1.parquet` (Subsystem A — Definition B, TCE population)

The v1 TCE population the MegaMiner pipeline operates on: every SPOC FFI
TCE, aggregated across sectors, with stellar parameters and selection
flags. Produced by `src/tess_megastructures/ingest/tce_sample.py`.

**This is Definition B (the TCE population), NOT the stellar
occurrence-rate denominator (Definition A / "parent sample"), which is
deferred to v2.** See decisions.md (Definition A/B entry).

One row per `(tic_id, planet_number, sector)`. Contains all columns from
`tce_dv_metrics_*.parquet` (carried through aggregation) plus:

| Column | Type | Source | Definition |
|---|---|---|---|
| `run_type` | string | derived | `"single_sector"` or `"multi_sector"` (from `n_difference_images`) |
| `has_doyle_params` | bool | derived | Whether the TIC matched the Doyle+24 cross-match |
| `doyle_*` | various | Doyle+24 | Gaia-derived params, prefixed to avoid clobbering DV params (e.g. `doyle_ruwe`, `doyle_parallax_over_error`) |
| `passed_tmag_cut` | bool | derived | `tess_mag` within config range |
| `passed_log_g_cut` | bool | derived | `log_g` >= config threshold (main sequence) |
| `passed_parallax_cut` | bool | derived | `doyle_parallax_over_error` >= threshold (null if no Doyle match) |
| `passed_ruwe_cut` | bool | derived | `doyle_ruwe` < threshold (null if no Doyle match) |
| `has_valid_stellar_params` | bool | derived | All `require_valid` columns non-null |
| `in_clean_sample` | bool | derived | AND of the `required_for_clean` cuts |
| `tce_sample_version` | string | config | Sample version tag |
| `built_with_package_version` | string | derived | Package version at build time |
| `built_at` | string | derived | UTC ISO timestamp |

Stellar params: DV-extracted columns (`effective_temp`, `radius`,
`log_g`, `tess_mag`) are PRIMARY (complete coverage). Doyle+24 columns
(`doyle_*`) are an ENRICHMENT layer, present only where the TIC
cross-match hits. Rows are never dropped; failing a cut sets the flag
False but keeps the row.

---

## `parent_sample_v1.parquet` (Subsystem A — Definition A, DEFERRED to v2)

The stellar occurrence-rate denominator: one row per searched TIC,
including stars that produced no TCE. Required only for upper-limit
calculations, which are a v2/future deliverable. **Not built for v1.**
The stub in `src/tess_megastructures/ingest/parent_sample.py` is a
placeholder. Schema TBD when v2 work begins.

---

## Subsystem B columns (added to `tce_sample_v1.parquet`)

Subsystem B does not produce a separate file. It adds derived metrics and
boolean flag columns in place on `tce_sample_v1.parquet` during the build.
Flags use the convention **True = suspicious** (opposite polarity from the
`passed_*` stellar cuts, where True = good). Rows are never dropped.

Produced by `src/tess_megastructures/annotate/derived_metrics.py` and
`src/tess_megastructures/annotate/diagnostics.py`. Thresholds come from the
`diagnostics:` block of `configs/tce_sample_v1.yaml`.

### Derived metrics

| Column | Type | Source | Definition |
|---|---|---|---|
| `model_chi_square_reduced` | float64 | derived | `model_chi_square / model_degrees_of_freedom` |
| `odd_even_depth_sig` | float64 | derived | `sqrt(odd_even_depth_statistic)` |
| `ghost_diagnostic_ratio` | float64 | derived | `ghost_core_correlation / ghost_halo_correlation` |
| `matching_period_signals` | bool | derived | TIC has >=2 TCEs with periods within `period_match_tol_days` |

### Diagnostic flags (True = suspicious)

| Column | Type | Source | Definition |
|---|---|---|---|
| `flag_suspected_eb` | bool | derived | SPOC `suspected_eclipsing_binary` is True |
| `flag_no_convergence` | bool | derived | `full_convergence` is False |
| `flag_invalid_odd_even` | bool | derived | `odd_even_depth_significance == -1` (DV sentinel) |
| `flag_background_eb` | bool | derived | `ghost_diagnostic_ratio < ghost_ratio_min` |
| `flag_centroid_offset` | bool | derived | off-target: both aperture offsets >= `centroid_offset_max_sigma` |
| `flag_matching_period` | bool | derived | `matching_period_signals` is True |
| `flag_large_odd_even` | bool | derived | `odd_even_depth_sig > odd_even_sig_max` |
| `flag_low_snr` | bool | derived | `model_fit_snr < snr_min` |
| `flag_low_rchisq` | bool | derived | `model_chi_square_reduced < reduced_chisq_min` |
| `any_diagnostic_flag` | bool | derived | OR of all `flag_*` columns |

NaN policy: a flag fires only on positive evidence; missing data is never
flagged. The catalog cross-match flag (`flag_catalog_binary`) is not yet
implemented. See `docs/per_subsystem/B_annotate.md`.

## `vetting_queue.parquet` (Subsystem C)

Subset of the annotated table selected for human/LLM review.

TODO: Document after candidate selection is implemented.

## `vetting_log.sqlite` (Subsystem C)

Schema documented in `src/tess_megastructures/vet/log.py`.
