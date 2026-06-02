# Subsystem B: annotate

Adds derived diagnostic metrics and boolean filter flags to the TCE sample.
Implements the vetting logic inherited from Isabel Angelo's
`create_tce_batches.py`, rebuilt as **flags, not cuts**: every diagnostic
produces a boolean column and no rows are ever dropped. Candidate selection
becomes a query over the flags (and, later, ML scores) rather than a
destructive filter chain.

See `docs/architecture.md` for the high-level design and the module
docstrings in `src/tess_megastructures/annotate/` for implementation detail.

## Inputs

The aggregated, Doyle-enriched TCE table produced inside
`build_tce_sample` (Subsystem A). All required columns come straight from
the parser output (`tce_dv_metrics_<sector>.parquet`); no external data is
needed for the DV-intrinsic flags.

## Outputs

Columns added in place on `tce_sample_v1.parquet`. Two groups:

**Derived metrics** (`annotate/derived_metrics.py`):

| Column | Definition |
|---|---|
| `model_chi_square_reduced` | `model_chi_square / model_degrees_of_freedom` |
| `odd_even_depth_sig` | `sqrt(odd_even_depth_statistic)` |
| `ghost_diagnostic_ratio` | `ghost_core_correlation / ghost_halo_correlation` |
| `matching_period_signals` | bool: TIC has >=2 TCEs with periods within `period_match_tol_days` (default 0.01 d) |

**Diagnostic flags** (`annotate/diagnostics.py`) — `True` means the TCE is
**flagged as suspicious** for that diagnostic (the opposite polarity from the
`passed_*` stellar cuts, where `True` means good):

| Flag | Fires when | Threshold key |
|---|---|---|
| `flag_suspected_eb` | `suspected_eclipsing_binary` is True (SPOC EB flag) | — |
| `flag_no_convergence` | `full_convergence` is False | — |
| `flag_invalid_odd_even` | `odd_even_depth_significance == -1` (DV sentinel) | `odd_even_invalid_sentinel` |
| `flag_background_eb` | `ghost_diagnostic_ratio < ghost_ratio_min` (blended/background EB) | `ghost_ratio_min` |
| `flag_centroid_offset` | signal off-target (both aperture offsets >= threshold) | `centroid_offset_max_sigma` |
| `flag_matching_period` | `matching_period_signals` is True | `period_match_tol_days` |
| `flag_large_odd_even` | `odd_even_depth_sig > odd_even_sig_max` (likely EB) | `odd_even_sig_max` |
| `flag_low_snr` | `model_fit_snr < snr_min` | `snr_min` |
| `flag_low_rchisq` | `model_chi_square_reduced < reduced_chisq_min` (well-fit, less anomalous) | `reduced_chisq_min` |

Plus `any_diagnostic_flag` (bool): True if any flag above is set. The
"unflagged survivors" are the rows with `any_diagnostic_flag == False`.

**NaN policy:** a flag fires only on positive evidence the diagnostic is
tripped. Missing data (NaN) is never flagged — we do not mark a TCE
suspicious merely because a metric is absent. This is the conservative
choice for an anomaly search.

The catalog cross-match flag (`flag_catalog_binary` and known-object flags)
is **not yet implemented**; it depends on the catalog loaders and lives in
`annotate/catalog_xmatch.py` (stub). See Open questions.

## Configuration

Thresholds live under the `diagnostics:` block of `configs/tce_sample_v1.yaml`.
They are Isabel's inherited values and are PLACEHOLDERS pending science
calibration. Changing a threshold is a one-line config edit with no code
change.

## Key files

- `src/tess_megastructures/annotate/derived_metrics.py` — derived quantities
- `src/tess_megastructures/annotate/diagnostics.py` — boolean flags + `any_diagnostic_flag`
- `src/tess_megastructures/annotate/catalog_xmatch.py` — catalog cross-match (stub)
- `scripts/build_tce_sample.py` — driver; calls the annotate functions and prints flag counts
- `scripts/make_dashboard.py` — HTML inspection report (see below)
- `configs/tce_sample_v1.yaml` — `diagnostics:` thresholds
- Tests: `tests/test_derived_metrics.py`, `tests/test_diagnostics.py`,
  `tests/test_tce_sample_diagnostics.py`

## Inspection dashboard

`scripts/make_dashboard.py` turns a built sample into a single self-contained
HTML report (no external dependencies, works offline, emailable). Inspection
only — it never modifies the sample.

```bash
uv run python scripts/make_dashboard.py path/to/tce_sample_v1.parquet
# writes path/to/tce_sample_v1_dashboard.html
# optional: -o OUTPUT.html
```

If the sample lives on the node, generate there and copy the HTML down:

```bash
# on the node
uv run python scripts/make_dashboard.py /mnt/buf0/<user>/outputs/tce_sample_v1.parquet
# on your laptop
scp <user>@tarang-node1.hcro.org:/mnt/buf0/<user>/outputs/tce_sample_v1_dashboard.html ~/Downloads/
```

The report shows:

- **Stat cards** — TCE count, unique TICs, in-clean-sample, unflagged survivors
- **Funnel** — total -> clean sample -> unflagged survivors
- **Diagnostic flags** and **Stellar cuts** — per-flag/per-cut bars with counts and percentages
- **Distributions** — depth, period, reduced chi-squared, SNR, Tmag, Teff, with labelled axes (log-binned where skewed; axis ticks show real values)
- **Flag co-occurrence** — which flags tend to fire together
- **Unflagged survivors** — sortable table of the TCEs that tripped no diagnostic

## Open questions

- **Catalog cross-match philosophy** (under discussion with the team): which
  catalogs to include, and whether catalog membership is a hard exclusion or a
  flag (consistent with flags-not-cuts). Drives the build of
  `catalog_xmatch.py`.
- **Threshold calibration:** all diagnostic thresholds are Isabel's inherited
  placeholders. They need calibration against a known-anomaly validation set.
  `reduced_chisq_min` dominates the survivor count, so it matters most.
- **Deep-eclipse EBs:** symmetric, on-target eclipsing binaries with large
  depths pass the current flags. A depth-based flag and/or the EB-catalog
  cross-match would catch them (see decisions.md, deep-eclipse finding).
