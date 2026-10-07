"""Generate a static HTML inspection report from a TCE sample Parquet.

Reads a tce_sample_v1.parquet (the output of build_tce_sample) and writes a
single self-contained HTML file with no external dependencies. Sections, top
to bottom:

  Summary           independent gate counts (fractions of total) + survivors
  Stellar cuts      with parameter ranges (informational; do NOT gate)
  Diagnostic flags  with cutoff values where appropriate (gate survivors)
  Catalog flags     vetted-EB cross-match, own section (gate survivors)
  Distributions     histograms
  Flag co-occurrence
  Unflagged survivors  table, incl. unvetted-catalog annotation column

Threshold values shown on labels are read from the Parquet's embedded metadata
(written by build_tce_sample), so they always reflect the thresholds actually
used to build this sample -- no config drift. If the metadata is absent (older
parquet), labels degrade gracefully to no parenthetical.

IMPORTANT -- this dashboard depicts the CURRENT pipeline, which computes flags
in PARALLEL on the full population. Stellar cuts are informational and do NOT
currently gate the survivor set (a survivor must have no diagnostic flag and no
catalog flag; it need not be in the clean sample). The Summary makes this
explicit rather than implying a sequential funnel.

Usage
-----
    uv run python scripts/make_dashboard.py INPUT.parquet [-o OUTPUT.html]
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --- diagnostic flags that GATE survivors (DV-intrinsic). order = display order.
DIAGNOSTIC_FLAG_COLUMNS = [
    "flag_suspected_eb",
    "flag_no_convergence",
    "flag_invalid_odd_even",
    "flag_background_eb",
    "flag_centroid_offset",
    "flag_matching_period",
    "flag_large_odd_even",
    "flag_low_snr",
]

# --- catalog flags that GATE survivors. shown in their OWN section.
#     flag_catalog_eb is the combined (gating) flag; the per-source flags are
#     the components. Titles per spec.
CATALOG_FLAG_TITLES = {
    "flag_prsa_eb": "Prša et al. (2022) Vetted EB Catalog",
    "flag_kostov_eb": "Kostov et al. (2025) Vetted EB Catalog",
    "flag_oddo_eb": "Oddo et al. (2025) M+M EB Catalog",
    "flag_calnet_eb": "Shan et al. (2025) CALNet EB Catalog (ML-derived, 2-min)",
    "flag_catalog_eb": "Combined Catalog EBs",
}
CATALOG_FLAG_ORDER = [
    "flag_prsa_eb",
    "flag_kostov_eb",
    "flag_oddo_eb",
    "flag_calnet_eb",
    "flag_catalog_eb",
]

# DOI links for each per-source catalog (Combined has no single source).
CATALOG_FLAG_LINKS = {
    "flag_prsa_eb": "https://doi.org/10.3847/1538-4365/ac324a",
    "flag_kostov_eb": "https://doi.org/10.3847/1538-4365/ade2d8",
    "flag_oddo_eb": "https://doi.org/10.3847/1538-4357/ae0c0f",
    "flag_calnet_eb": "https://doi.org/10.48550/arXiv.2504.15875",
}

# --- stellar cuts (informational; do NOT gate). base labels.
CUT_LABELS = {
    "passed_tmag_cut": "Tmag in range",
    "passed_log_g_cut": "Surface gravity (log g",  # closing paren added with threshold
    "passed_parallax_cut": "Parallax S/N",
    "passed_ruwe_cut": "RUWE",
}
CUT_ORDER = ["passed_tmag_cut", "passed_log_g_cut", "passed_parallax_cut", "passed_ruwe_cut"]

# base labels for diagnostic flags (cutoff suffix added from metadata).
DIAG_BASE_LABELS = {
    "flag_suspected_eb": "Suspected eclipsing binary (SPOC)",
    "flag_no_convergence": "Transit fit did not converge",
    "flag_invalid_odd_even": "Invalid odd/even statistic",
    "flag_background_eb": "Background / blended EB (ghost",
    "flag_centroid_offset": "Off-target centroid offset",
    "flag_matching_period": "Matching-period signals",
    "flag_large_odd_even": "Large odd/even depth difference",
    "flag_low_snr": "Low S/N",
}


def _fmt(x) -> str:
    """Format a threshold: drop trailing .0 from integer-valued floats."""
    if x is None:
        return ""
    if isinstance(x, (int, float)) and float(x).is_integer():
        return str(int(x))
    return str(x)


def _read_thresholds(path: Path) -> dict:
    """Read embedded threshold metadata from the Parquet. {} if absent."""
    try:
        import pyarrow.parquet as pq

        meta = pq.read_schema(path).metadata or {}
        key = b"tess_megastructures_thresholds"
        if key not in meta:
            return {}
        return json.loads(meta[key].decode("utf-8"))
    except Exception:  # noqa: BLE001 -- any failure -> graceful no-metadata
        return {}


def _diag_label(col: str, diag: dict) -> str:
    base = DIAG_BASE_LABELS.get(col, col.replace("flag_", "").replace("_", " "))
    g = diag.get
    suffix = ""
    if col == "flag_background_eb" and g("ghost_ratio_min") is not None:
        suffix = f" ratio &lt; {_fmt(g('ghost_ratio_min'))})"
    elif col == "flag_centroid_offset" and g("centroid_offset_max_sigma") is not None:
        suffix = f" (&gt; {_fmt(g('centroid_offset_max_sigma'))}\u03c3)"
    elif col == "flag_large_odd_even" and g("odd_even_sig_max") is not None:
        suffix = f" (&gt; {_fmt(g('odd_even_sig_max'))})"
    elif col == "flag_low_snr" and g("snr_min") is not None:
        suffix = f" (&lt; {_fmt(g('snr_min'))})"
    elif col == "flag_matching_period" and g("period_match_tol_days") is not None:
        suffix = f" (within {_fmt(g('period_match_tol_days'))} d)"
    return base + suffix


def _cut_label(col: str, stel: dict) -> str:
    base = CUT_LABELS.get(col, col.replace("passed_", "").replace("_", " "))
    s = stel.get
    suffix = ""
    if col == "passed_tmag_cut" and s("tmag_min") is not None and s("tmag_max") is not None:
        suffix = f" ({_fmt(s('tmag_min'))}\u2013{_fmt(s('tmag_max'))})"
    elif col == "passed_log_g_cut" and s("log_g_min") is not None:
        suffix = f" \u2265 {_fmt(s('log_g_min'))})"
    elif col == "passed_parallax_cut" and s("parallax_over_error_min") is not None:
        suffix = f" (\u2265 {_fmt(s('parallax_over_error_min'))})"
    elif col == "passed_ruwe_cut" and s("ruwe_max_for_clean") is not None:
        suffix = f" (&lt; {_fmt(s('ruwe_max_for_clean'))})"
    return base + suffix


def _sector_str(df: pd.DataFrame) -> str:
    if "sector" not in df.columns:
        return "unknown"
    secs = sorted(pd.to_numeric(df["sector"], errors="coerce").dropna().unique())
    if not secs:
        return "unknown"
    secs = [int(s) for s in secs]
    if len(secs) == 1:
        return f"s{secs[0]:04d}"
    return ", ".join(f"s{s:04d}" for s in secs)


def mast_dvr_url(tic_id, sector) -> str | None:
    try:
        tic_int = int(tic_id)
        sec_int = int(sector)
    except (TypeError, ValueError):
        return None
    ticz = f"{tic_int:016d}"
    seg = "/".join(ticz[i : i + 4] for i in range(0, 16, 4))
    s = f"s{sec_int:04d}"
    fn = f"hlsp_tess-spoc_tess_phot_{ticz}-{s}-{s}_tess_v1_dvm.pdf"
    return (
        "https://mast.stsci.edu/api/v0.1/Download/file/"
        f"?uri=mast:HLSP/tess-spoc/{s}/target/{seg}/{fn}"
    )


SURVIVOR_COLUMNS = [
    "tic_id",
    "planet_number",
    "sector",
    "orbital_period_days",
    "transit_depth_ppm",
    "tess_mag",
    "effective_temp",
    "has_doyle_params",
    "model_chi_square_reduced",
    "model_fit_snr",
    "toi_id",
]


def _read(path: Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)


def _bool_count(df: pd.DataFrame, col: str) -> int:
    s = df[col]
    return int(s.sum() if s.dtype == "bool" else s.fillna(False).astype(bool).sum())


def _bar(
    label: str, value: int, total: int, color: str = "#60d39f", label_is_html: bool = False
) -> str:
    pct = (value / total * 100) if total else 0
    lbl = label if label_is_html else html.escape(label)
    return f"""
    <div class="row">
      <div class="rlabel">{lbl}</div>
      <div class="track"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div>
      <div class="rval">{value:,}<span class="pct"> / {total:,} ({pct:.1f}%)</span></div>
    </div>"""


def _histogram_svg(values: pd.Series, title: str, bins: int = 30, log_x: bool = False) -> str:
    import numpy as np

    v = pd.to_numeric(values, errors="coerce").dropna()
    if v.empty:
        return f"<div class='hist'><div class='htitle'>{html.escape(title)}</div><div class='empty'>no data</div></div>"
    plot_v = v.copy()
    if log_x:
        plot_v = plot_v[plot_v > 0]
        if plot_v.empty:
            return f"<div class='hist'><div class='htitle'>{html.escape(title)}</div><div class='empty'>no positive data</div></div>"
        plot_v = np.log10(plot_v)
    counts, edges = pd.cut(plot_v, bins=bins, retbins=True)
    hist = counts.value_counts(sort=False).to_numpy()
    maxc = int(hist.max()) if hist.max() > 0 else 1
    w, h = 560, 300
    ml, mr, mt, mb = 56, 12, 10, 40
    pw, ph = w - ml - mr, h - mt - mb
    bw = pw / len(hist)

    def fmt(x: float) -> str:
        ax = abs(x)
        if ax != 0 and (ax >= 1e4 or ax < 1e-2):
            return f"{x:.1e}"
        if ax >= 100:
            return f"{x:,.0f}"
        if ax >= 1:
            return f"{x:.1f}"
        return f"{x:.2g}"

    bars = []
    for i, c in enumerate(hist):
        bh = (c / maxc) * ph
        x = ml + i * bw
        y = mt + ph - bh
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(bw - 1, 0.5):.1f}" height="{bh:.1f}" fill="#61d8e4"/>'
        )
    axes = (
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt + ph}" stroke="rgba(244,240,230,0.35)" stroke-width="1"/>'
        f'<line x1="{ml}" y1="{mt + ph}" x2="{ml + pw}" y2="{mt + ph}" stroke="rgba(244,240,230,0.35)" stroke-width="1"/>'
    )
    yticks = []
    for frac in (0.0, 0.5, 1.0):
        cval = int(round(maxc * frac))
        ty = mt + ph - frac * ph
        yticks.append(
            f'<line x1="{ml - 4}" y1="{ty:.1f}" x2="{ml}" y2="{ty:.1f}" stroke="rgba(244,240,230,0.35)" stroke-width="1"/>'
            f'<text x="{ml - 7}" y="{ty + 3:.1f}" text-anchor="end" class="tick">{cval:,}</text>'
        )
    xticks = []
    lo_edge, hi_edge = edges[0], edges[-1]
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        edge_val = lo_edge + frac * (hi_edge - lo_edge)
        real_val = (10**edge_val) if log_x else edge_val
        tx = ml + frac * pw
        xticks.append(
            f'<line x1="{tx:.1f}" y1="{mt + ph}" x2="{tx:.1f}" y2="{mt + ph + 4}" stroke="rgba(244,240,230,0.35)" stroke-width="1"/>'
            f'<text x="{tx:.1f}" y="{mt + ph + 16:.1f}" text-anchor="middle" class="tick">{fmt(real_val)}</text>'
        )
    axis_note = " (log scale)" if log_x else ""
    xaxis_label = f'<text x="{ml + pw / 2:.1f}" y="{h - 2}" text-anchor="middle" class="axislabel">value{axis_note}</text>'
    yaxis_label = (
        f'<text x="12" y="{mt + ph / 2:.1f}" text-anchor="middle" class="axislabel" '
        f'transform="rotate(-90 12 {mt + ph / 2:.1f})">count</text>'
    )
    return f"""
    <div class="hist">
      <div class="htitle">{html.escape(title)}</div>
      <svg viewBox="0 0 {w} {h}" class="histsvg">
        {"".join(bars)}{axes}{"".join(yticks)}{"".join(xticks)}{xaxis_label}{yaxis_label}
      </svg>
      <div class="hsub">n={len(v):,} &middot; median {v.median():,.4g} &middot; range {v.min():,.4g} to {v.max():,.4g}</div>
    </div>"""


def _scatter_svg(
    x: pd.Series,
    y: pd.Series,
    title: str,
    x_label: str,
    y_label: str,
    log_x: bool = False,
    log_y: bool = False,
) -> str:
    """Small SVG scatter plot. Used for ExoMiner score vs reduced chi-squared."""
    import numpy as np

    xv = pd.to_numeric(x, errors="coerce")
    yv = pd.to_numeric(y, errors="coerce")
    mask = xv.notna() & yv.notna()
    if log_x:
        mask &= xv > 0
    if log_y:
        mask &= yv > 0
    xv, yv = xv[mask], yv[mask]
    if xv.empty:
        return f"<div class='hist'><div class='htitle'>{html.escape(title)}</div><div class='empty'>no data</div></div>"
    px = np.log10(xv) if log_x else xv.to_numpy(dtype=float)
    py = np.log10(yv) if log_y else yv.to_numpy(dtype=float)
    w, h = 560, 360
    ml, mr, mt, mb = 60, 14, 12, 46
    pw, ph = w - ml - mr, h - mt - mb
    xlo, xhi = float(px.min()), float(px.max())
    ylo, yhi = float(py.min()), float(py.max())
    xrng = (xhi - xlo) or 1.0
    yrng = (yhi - ylo) or 1.0

    def sx(v):
        return ml + (v - xlo) / xrng * pw

    def sy(v):
        return mt + ph - (v - ylo) / yrng * ph

    dots = "".join(
        f'<circle cx="{sx(px[i]):.1f}" cy="{sy(py[i]):.1f}" r="2.4" fill="#61d8e4" fill-opacity="0.55"/>'
        for i in range(len(px))
    )
    axes = (
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt + ph}" stroke="rgba(244,240,230,0.35)"/>'
        f'<line x1="{ml}" y1="{mt + ph}" x2="{ml + pw}" y2="{mt + ph}" stroke="rgba(244,240,230,0.35)"/>'
    )

    def fmt(v, is_log):
        real = 10**v if is_log else v
        a = abs(real)
        if a != 0 and (a >= 1e4 or a < 1e-2):
            return f"{real:.0e}"
        if a >= 100:
            return f"{real:,.0f}"
        if a >= 1:
            return f"{real:.1f}"
        return f"{real:.2g}"

    ticks = ""
    for frac in (0.0, 0.5, 1.0):
        xt = ml + frac * pw
        ticks += (
            f'<line x1="{xt:.1f}" y1="{mt + ph}" x2="{xt:.1f}" y2="{mt + ph + 4}" stroke="rgba(244,240,230,0.35)"/>'
            f'<text x="{xt:.1f}" y="{mt + ph + 16:.1f}" text-anchor="middle" class="tick">{fmt(xlo + frac * xrng, log_x)}</text>'
        )
        yt = mt + ph - frac * ph
        ticks += (
            f'<line x1="{ml - 4}" y1="{yt:.1f}" x2="{ml}" y2="{yt:.1f}" stroke="rgba(244,240,230,0.35)"/>'
            f'<text x="{ml - 7}" y="{yt + 3:.1f}" text-anchor="end" class="tick">{fmt(ylo + frac * yrng, log_y)}</text>'
        )
    xlab = f'<text x="{ml + pw / 2:.1f}" y="{h - 4}" text-anchor="middle" class="axislabel">{html.escape(x_label)}{" (log)" if log_x else ""}</text>'
    ylab = (
        f'<text x="14" y="{mt + ph / 2:.1f}" text-anchor="middle" class="axislabel" '
        f'transform="rotate(-90 14 {mt + ph / 2:.1f})">{html.escape(y_label)}{" (log)" if log_y else ""}</text>'
    )
    return f"""
    <div class="hist">
      <div class="htitle">{html.escape(title)}</div>
      <svg viewBox="0 0 {w} {h}" class="histsvg">{dots}{axes}{ticks}{xlab}{ylab}</svg>
      <div class="hsub">n={len(px):,}</div>
    </div>"""


def _cooccurrence_table(df: pd.DataFrame, flag_cols: list[str]) -> str:
    if not flag_cols:
        return "<p class='empty'>No flag columns found.</p>"
    bdf = df[flag_cols].fillna(False).astype(bool)
    short = [c.replace("flag_", "") for c in flag_cols]
    header = "".join(f"<th class='rot'><div>{html.escape(s)}</div></th>" for s in short)
    rows = []
    for i, ci in enumerate(flag_cols):
        cells = []
        for j, cj in enumerate(flag_cols):
            both = int((bdf[ci] & bdf[cj]).sum())
            if i == j:
                cells.append(f"<td class='diag'>{both:,}</td>")
            else:
                base = int(bdf[ci].sum()) or 1
                frac = both / base
                cells.append(f"<td style='background:rgba(96,211,159,{frac:.2f})'>{both:,}</td>")
        rows.append(f"<tr><th class='rowlab'>{html.escape(short[i])}</th>{''.join(cells)}</tr>")
    return f"""
    <table class="cooc"><tr><th></th>{header}</tr>{"".join(rows)}</table>
    <p class="note">Cell = number of TCEs tripping both flags. Row shading is relative to the
    row flag's own total (diagonal).</p>"""


def _survivor_table(df: pd.DataFrame, scores: pd.DataFrame | None = None) -> str:
    import json as _json

    unflagged = (
        df[~df["any_diagnostic_flag"].fillna(False).astype(bool)]
        if "any_diagnostic_flag" in df.columns
        else df.iloc[0:0]
    )
    if unflagged.empty:
        return "<p class='empty'>No unflagged survivors.</p>"
    unflagged = unflagged.copy()

    # Merge ExoMiner score columns (left-join on tic_id, planet_number).
    exo_cols = ["score", "median_z_score", "EB_score"]
    exo_present: list[str] = []
    if (
        scores is not None
        and not scores.empty
        and {"tic_id", "planet_number"}.issubset(scores.columns)
    ):
        exo_present = [c for c in exo_cols if c in scores.columns]
        if exo_present:
            unflagged = unflagged.drop(columns=[c for c in exo_present if c in unflagged.columns])
            keep = ["tic_id", "planet_number", *exo_present]
            unflagged = unflagged.merge(
                scores[keep].drop_duplicates(subset=["tic_id", "planet_number"]),
                on=["tic_id", "planet_number"],
                how="left",
            )
            if "score" in unflagged.columns:
                unflagged = unflagged.sort_values("score", na_position="last")

    n_total = len(unflagged)

    # Columns shown in the table (curated), then ExoMiner cols, then annotation.
    display_cols = [c for c in SURVIVOR_COLUMNS if c in unflagged.columns]
    display_cols += [c for c in exo_present if c not in display_cols]
    has_annot = "annotation_kostov_candidate" in unflagged.columns

    # All underlying columns (for CSV export of everything).
    all_cols = list(unflagged.columns)

    # Default-visible FILTER controls.
    # numeric range filters (only those present):
    range_filter_cols = [
        c
        for c in [
            *exo_present,  # score, median_z_score, EB_score
            "model_fit_snr",
            "model_chi_square_reduced",
            "orbital_period_days",
            "transit_depth_ppm",
            "transit_duration_hours",
            "ratio_planet_radius_to_star_radius",
            "odd_even_depth_sig",
            "ghost_diagnostic_ratio",
            "tess_mag",
            "effective_temp",
            "radius",
            "doyle_ruwe",
            "doyle_parallax_over_error",
        ]
        if c in unflagged.columns
    ]
    # boolean toggles (only annotation/stellar ones that actually vary for survivors):
    toggle_cols = [
        c
        for c in [
            "annotation_kostov_candidate",
            "annotation_low_rchisq",
            "passed_tmag_cut",
            "passed_log_g_cut",
            "passed_parallax_cut",
            "passed_ruwe_cut",
            "has_doyle_params",
            "in_clean_sample",
        ]
        if c in unflagged.columns
    ]
    # doyle_nss is really a binary flag -> toggle
    if "doyle_nss" in unflagged.columns:
        toggle_cols.append("doyle_nss")
    # exact-match dropdowns:
    select_cols = [c for c in ["sector", "planet_number"] if c in unflagged.columns]

    # Build JSON records (all columns). Convert non-JSON types.
    def _clean(v):
        if isinstance(v, float) and pd.isna(v):
            return None
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, bool):
            return v
        try:
            import math

            if isinstance(v, float) and (math.isinf(v)):
                return None
        except Exception:
            pass
        return v if (v is None or isinstance(v, (int, float, bool, str))) else str(v)

    records = [{c: _clean(r[c]) for c in all_cols} for _, r in unflagged.iterrows()]
    data_json = _json.dumps(records)
    # config for JS
    cfg = {
        "displayCols": display_cols,
        "exoCols": exo_present,
        "allCols": all_cols,
        "rangeCols": range_filter_cols,
        "toggleCols": toggle_cols,
        "selectCols": select_cols,
        "hasAnnot": has_annot,
    }
    # distinct values for select dropdowns
    selopts = {c: sorted({_clean(v) for v in unflagged[c].dropna().tolist()}) for c in select_cols}
    cfg["selectOptions"] = selopts
    cfg_json = _json.dumps(cfg)

    note_exo = ""
    if exo_present:
        note_exo = (
            " Shaded columns are ExoMiner outputs; default sort is ascending by score. "
            "Low score = un-planet-like, but the low-score tail is EB/variable-enriched, "
            "so treat score as a diagnostic, not a ranking."
        )
    note_annot = (
        ' The "annotation" toggles do not affect survivor status; they label rows.'
        if has_annot
        else ""
    )

    return f"""
    <div id="survFilters" class="filters"></div>
    <div class="survbar">
      <span id="survCount" class="survcount"></span>
      <span class="survbtns">
        <button type="button" id="dlFiltered" class="dlbtn">Download filtered CSV</button>
        <button type="button" id="dlAll" class="dlbtn">Download all CSV</button>
        <button type="button" id="resetFilters" class="dlbtn resetbtn">Reset filters</button>
      </span>
    </div>
    <div class="survscroll">
      <table class="survivors" id="survivors"><thead id="survHead"></thead><tbody id="survBody"></tbody></table>
    </div>
    <p class="note">{n_total:,} unflagged TCEs (no diagnostic and no catalog flag).
    Filter with the controls above (blank range = unbounded on that side; rows with no
    value in a filtered column are excluded by a range filter). Click a column header to
    sort. CSV export includes all {len(all_cols)} underlying columns.{note_exo}{note_annot}</p>
    <script id="survData" type="application/json">{data_json}</script>
    <script id="survCfg" type="application/json">{cfg_json}</script>
    """


def _exominer_section(df: pd.DataFrame, scores: pd.DataFrame | None, public: bool = False) -> str:
    """Render the ExoMiner-scores section, or empty string if no scores given.

    Cautious framing: scores are shown as a DIAGNOSTIC (distributions + the
    score-vs-reduced-chisq plot + a scored table), NOT as an anomaly ranking.
    The low-score tail is enriched in missed EBs / variables, not necessarily
    anomalies, so the dashboard does not present a "top candidates" leaderboard.
    """
    if scores is None or scores.empty:
        return ""
    if "score" not in scores.columns:
        return ""

    n_scored = int(scores["score"].notna().sum())
    n_surv = (
        int((~df["any_diagnostic_flag"].fillna(False).astype(bool)).sum())
        if "any_diagnostic_flag" in df.columns
        else len(scores)
    )

    # scored-plots-only section (the scores themselves are merged into the
    # survivor table; here we show the population-level diagnostic plots).
    hist_score = _histogram_svg(scores["score"], "ExoMiner score", log_x=True)
    hist_z = (
        _histogram_svg(scores["median_z_score"], "Median z-score", log_x=False)
        if "median_z_score" in scores.columns
        else ""
    )
    scatter = (
        _scatter_svg(
            scores["score"],
            scores["model_chi_square_reduced"],
            "ExoMiner score vs reduced chi-squared",
            "ExoMiner score",
            "reduced chi-squared",
            log_x=True,
            log_y=True,
        )
        if "model_chi_square_reduced" in scores.columns
        else ""
    )

    per_candidate_note = (
        "Per-candidate scores are available with the preliminary survivor list (on request)."
        if public
        else "Per-candidate scores are in the survivor table below (shaded columns)."
    )
    return f"""
<h2>ExoMiner scores</h2>
<p class="secsub">ExoMiner planet-likeness scores for the {n_scored:,} scored survivors
(of {n_surv:,}). Shown as a diagnostic, not an anomaly ranking: a low score means
un-planet-like, but the low-score tail is enriched in eclipsing binaries and
variables that passed the DV diagnostics, not necessarily anomalies. Use median
z-score and the score vs reduced chi-squared structure together, alongside manual
vetting, rather than score alone. {per_candidate_note}</p>
<div class="hists">{hist_score}{hist_z}{scatter}</div>"""


def _request_access_panel(n_survivors: int) -> str:
    """Public-view replacement for the survivor table.

    Shows the survivor COUNT (an aggregate summary number, not the data) and a
    button linking to the access-request form. The request flow is: user submits
    the form -> maintainer is notified -> maintainer adds the requester's email
    to the access allowlist (e.g. Cloudflare Access) -> they reach the gated
    private dashboard. The survivor list itself is NOT in this file.
    """
    # Access-request Google Form. Update here if the form URL changes.
    request_form_url = "https://forms.gle/C6rweSEtFyHziMmU8"
    return f"""<div class="reqaccess">
  <p class="reqlead">This summary reflects <strong>{n_survivors:,}</strong> unflagged
  survivor candidates from the current processing run. The candidate list itself
  is part of our preliminary, unpublished results and is available to
  collaborators and sponsors on request.</p>
  <p><a class="reqbtn" href="{request_form_url}" target="_blank" rel="noopener noreferrer">Request access to preliminary results</a></p>
  <p class="reqnote">Access is granted per-person by the project team. Once
  approved, you'll be able to view the full survivor candidate list, which updates
  as we process additional TESS sectors. Please use the same email on the form
  that you'll use to log in.</p>
</div>"""


_SURVIVOR_FILTER_JS = r"""<script>
(function () {
  var dataEl = document.getElementById("survData");
  var cfgEl = document.getElementById("survCfg");
  if (!dataEl || !cfgEl) return;
  var DATA = JSON.parse(dataEl.textContent);
  var CFG = JSON.parse(cfgEl.textContent);
  var sortState = { col: null, asc: true };

  // Columns that hold identifier integers and must never be formatted with
  // grouping separators or scientific notation (they are IDs, not quantities).
  var ID_COLS = { "tic_id": 1, "toi_id": 1, "planet_number": 1, "sector": 1 };

  function fmt(v, col) {
    if (v === null || v === undefined) return "-";
    if (typeof v === "number") {
      if (!isFinite(v)) return "-";
      // Identifier columns: render the integer verbatim, no separators, no exp.
      if (ID_COLS[col]) {
        return Number.isInteger(v) ? String(v) : String(v);
      }
      var a = Math.abs(v);
      // Integers always render in full (TIC-sized values must not go to exp).
      if (Number.isInteger(v)) return v.toLocaleString();
      // Non-integer extremes use scientific notation.
      if (a !== 0 && (a >= 1e5 || a < 1e-3)) return v.toExponential(3);
      return v.toLocaleString(undefined, { maximumSignificantDigits: 4 });
    }
    return String(v);
  }

  // ---- build filter controls ----
  var fbox = document.getElementById("survFilters");
  var html = '';
  html += '<div class="frow"><label class="flabel">TIC ID</label>' +
          '<input type="text" id="f_tic" class="finput" placeholder="search tic_id..."></div>';
  CFG.selectCols.forEach(function (c) {
    var opts = (CFG.selectOptions[c] || []).map(function (o) { return '<option value="' + o + '">' + o + '</option>'; }).join("");
    html += '<div class="frow"><label class="flabel">' + c + '</label>' +
            '<select class="fselect" data-col="' + c + '"><option value="">any</option>' + opts + '</select></div>';
  });
  CFG.rangeCols.forEach(function (c) {
    html += '<div class="frow"><label class="flabel">' + c + '</label>' +
            '<input type="number" step="any" class="frange" data-col="' + c + '" data-bound="min" placeholder="min">' +
            '<span class="fdash">to</span>' +
            '<input type="number" step="any" class="frange" data-col="' + c + '" data-bound="max" placeholder="max"></div>';
  });
  CFG.toggleCols.forEach(function (c) {
    html += '<div class="frow"><label class="flabel">' + c + '</label>' +
            '<select class="ftoggle" data-col="' + c + '"><option value="">any</option>' +
            '<option value="true">true</option><option value="false">false</option></select></div>';
  });
  fbox.innerHTML = html;

  // ---- header ----
  var headCols = CFG.displayCols.slice();
  var thead = document.getElementById("survHead");
  var exoSet = {}; CFG.exoCols.forEach(function (c) { exoSet[c] = 1; });
  var hrow = "<tr>";
  headCols.forEach(function (c) {
    hrow += '<th class="' + (exoSet[c] ? "exocol" : "") + '" data-col="' + c + '">' + c + '</th>';
  });
  if (CFG.hasAnnot) { /* annotation already in toggles; keep DV report link col */ }
  hrow += '<th>DV report</th></tr>';
  thead.innerHTML = hrow;

  function mastUrl(tic, sector) {
    if (tic === null || sector === null || tic === undefined || sector === undefined) return null;
    var t = String(tic).padStart(16, "0");
    var seg = t.match(/.{1,4}/g).join("/");
    var s = String(sector).padStart(4, "0");
    var f = "hlsp_tess-spoc_tess_phot_" + t + "-s" + s + "-s" + s + "_tess_v1_dvm.pdf";
    return "https://mast.stsci.edu/api/v0.1/Download/file/?uri=mast:HLSP/tess-spoc/s" + s + "/target/" + seg + "/" + f;
  }

  // ---- filtering ----
  function getFilters() {
    var f = { tic: "", ranges: {}, toggles: {}, selects: {} };
    var tic = document.getElementById("f_tic");
    f.tic = tic ? tic.value.trim() : "";
    document.querySelectorAll(".frange").forEach(function (el) {
      var c = el.dataset.col, b = el.dataset.bound, v = el.value.trim();
      if (v === "") return;
      f.ranges[c] = f.ranges[c] || {};
      f.ranges[c][b] = parseFloat(v);
    });
    document.querySelectorAll(".ftoggle").forEach(function (el) {
      if (el.value !== "") f.toggles[el.dataset.col] = (el.value === "true");
    });
    document.querySelectorAll(".fselect").forEach(function (el) {
      if (el.value !== "") f.selects[el.dataset.col] = el.value;
    });
    return f;
  }

  function applyFilters(rows, f) {
    return rows.filter(function (row) {
      if (f.tic && String(row.tic_id).indexOf(f.tic) === -1) return false;
      for (var c in f.ranges) {
        var v = row[c];
        if (v === null || v === undefined || typeof v !== "number" || !isFinite(v)) return false;
        if (f.ranges[c].min !== undefined && v < f.ranges[c].min) return false;
        if (f.ranges[c].max !== undefined && v > f.ranges[c].max) return false;
      }
      for (var t in f.toggles) {
        if (Boolean(row[t]) !== f.toggles[t]) return false;
      }
      for (var s in f.selects) {
        if (String(row[s]) !== String(f.selects[s])) return false;
      }
      return true;
    });
  }

  function sortRows(rows) {
    if (!sortState.col) return rows;
    var c = sortState.col, asc = sortState.asc;
    return rows.slice().sort(function (a, b) {
      var x = a[c], y = b[c];
      var xn = (x === null || x === undefined), yn = (y === null || y === undefined);
      if (xn && yn) return 0;
      if (xn) return 1;       // nulls last
      if (yn) return -1;
      if (typeof x === "number" && typeof y === "number") return asc ? x - y : y - x;
      return asc ? String(x).localeCompare(String(y)) : String(y).localeCompare(String(x));
    });
  }

  var currentRows = [];

  function render() {
    var f = getFilters();
    var rows = applyFilters(DATA, f);
    rows = sortRows(rows);
    currentRows = rows;
    var tbody = document.getElementById("survBody");
    var out = "";
    rows.forEach(function (row) {
      out += "<tr>";
      headCols.forEach(function (c) {
        out += '<td class="' + (exoSet[c] ? "exocol" : "") + '">' + fmt(row[c], c) + "</td>";
      });
      var url = mastUrl(row.tic_id, row.sector);
      out += url ? '<td><a href="' + url + '" target="_blank" rel="noopener noreferrer">PDF</a></td>' : "<td>-</td>";
      out += "</tr>";
    });
    tbody.innerHTML = out;
    var cnt = document.getElementById("survCount");
    cnt.textContent = "showing " + rows.length + " of " + DATA.length + " survivors";
  }

  // ---- sort on header click ----
  document.getElementById("survHead").addEventListener("click", function (e) {
    var th = e.target.closest("th");
    if (!th || !th.dataset.col) return;
    var c = th.dataset.col;
    if (sortState.col === c) sortState.asc = !sortState.asc;
    else { sortState.col = c; sortState.asc = true; }
    render();
  });

  // ---- filter events ----
  fbox.addEventListener("input", render);
  fbox.addEventListener("change", render);
  document.getElementById("resetFilters").addEventListener("click", function () {
    fbox.querySelectorAll("input").forEach(function (el) { el.value = ""; });
    fbox.querySelectorAll("select").forEach(function (el) { el.value = ""; });
    render();
  });

  // ---- CSV export (all underlying columns) ----
  function toCSV(rows) {
    var cols = CFG.allCols;
    var lines = [cols.map(csvCell).join(",")];
    rows.forEach(function (row) {
      lines.push(cols.map(function (c) { return csvCell(row[c]); }).join(","));
    });
    return lines.join("\\n");
  }
  function csvCell(v) {
    if (v === null || v === undefined) return "";
    var s = String(v);
    if (s.indexOf(",") !== -1 || s.indexOf('"') !== -1 || s.indexOf("\\n") !== -1) {
      s = '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  }
  function download(name, text) {
    var blob = new Blob([text], { type: "text/csv" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }
  document.getElementById("dlFiltered").addEventListener("click", function () {
    download("survivors_filtered.csv", toCSV(currentRows));
  });
  document.getElementById("dlAll").addEventListener("click", function () {
    download("survivors_all.csv", toCSV(DATA));
  });

  render();
})();
</script>"""


def build_report(
    df: pd.DataFrame,
    source_name: str,
    thresholds: dict,
    scores: pd.DataFrame | None = None,
    view: str = "full",
) -> str:
    # view controls survivor-data exposure:
    #   "full"/"private" -> survivor table + its embedded JSON are included
    #   "public"         -> survivor table and JSON are OMITTED ENTIRELY
    #                       (not hidden -- absent from the file), replaced by a
    #                       request-access panel. This is the security boundary:
    #                       the public artifact must contain no survivor data.
    is_public = view == "public"
    n_total = len(df)
    diag = thresholds.get("diagnostics", {})
    stel = thresholds.get("stellar_cuts", {})

    present_diag = [c for c in DIAGNOSTIC_FLAG_COLUMNS if c in df.columns]
    present_cat = [c for c in CATALOG_FLAG_ORDER if c in df.columns]
    present_cuts = [c for c in CUT_ORDER if c in df.columns]

    # ---- Summary (independent gate counts as fractions of total) ----
    n_clean = _bool_count(df, "in_clean_sample") if "in_clean_sample" in df else 0
    n_unflag_diag = (
        int((~df[present_diag].fillna(False).astype(bool).any(axis=1)).sum())
        if present_diag
        else n_total
    )
    n_unflag_cat = (
        int((~df["flag_catalog_eb"].fillna(False).astype(bool)).sum())
        if "flag_catalog_eb" in df
        else n_total
    )
    n_any = _bool_count(df, "any_diagnostic_flag") if "any_diagnostic_flag" in df else 0
    n_survivors = n_total - n_any

    summary = _bar("Total TCEs", n_total, n_total, "#61d8e4")
    if "in_clean_sample" in df:
        summary += _bar(
            "In clean sample (stellar parameter cuts, informational)", n_clean, n_total, "#9aa2ff"
        )
    summary += _bar("Unflagged by diagnostic flags", n_unflag_diag, n_total, "#f2745f")
    summary += _bar("Unflagged by catalog flags", n_unflag_cat, n_total, "#9aa2ff")
    summary += _bar("Total unflagged survivors", n_survivors, n_total, "#60d39f")

    summary_note = (
        "<p class='note'>Flags are computed independently; each bar is a fraction of all TCEs. "
        "A survivor has no diagnostic flag and no catalog flag. Stellar parameter cuts do not gate.</p>"
    )

    # ---- Stellar cuts (with ranges) ----
    cut_bars = "".join(
        _bar(_cut_label(c, stel), _bool_count(df, c), n_total, "#9aa2ff", label_is_html=True)
        for c in present_cuts
    )

    # ---- Gaia cross-match coverage (TCEs with a Doyle/Gaia match -> valid stellar params) ----
    if "has_doyle_params" in df.columns:
        gaia_xmatch_bar = _bar(
            "Gaia cross-match (valid stellar parameters)",
            _bool_count(df, "has_doyle_params"),
            n_total,
            "#61d8e4",
        )
    else:
        gaia_xmatch_bar = ""

    # ---- Diagnostic flags (with cutoffs) ----
    diag_bars = "".join(
        _bar(_diag_label(c, diag), _bool_count(df, c), n_total, "#f2745f", label_is_html=True)
        for c in present_diag
    )

    # ---- Catalog flags (own section, three titled bars) ----
    def _cat_title(c: str) -> str:
        title = CATALOG_FLAG_TITLES[c]
        url = CATALOG_FLAG_LINKS.get(c)
        if url:
            return (
                f'<a href="{url}" target="_blank" rel="noopener noreferrer">'
                f"{html.escape(title)}</a>"
            )
        return html.escape(title)

    cat_bars = "".join(
        _bar(_cat_title(c), _bool_count(df, c), n_total, "#9aa2ff", label_is_html=True)
        for c in present_cat
    )
    n_annot = (
        _bool_count(df, "annotation_kostov_candidate") if "annotation_kostov_candidate" in df else 0
    )
    _kostov_url = CATALOG_FLAG_LINKS["flag_kostov_eb"]
    _annot_title = (
        f'<a href="{_kostov_url}" target="_blank" rel="noopener noreferrer">'
        "Kostov et al. (2025) Unvetted Candidates (annotation only)</a>"
    )
    cat_annot_bar = (
        _bar(_annot_title, n_annot, n_total, "#e9c85c", label_is_html=True)
        if "annotation_kostov_candidate" in df
        else ""
    )

    # ---- distributions ----
    hists = ""
    for col, title, logx in [
        ("transit_depth_ppm", "Transit depth (ppm)", True),
        ("orbital_period_days", "Orbital period (days)", True),
        ("model_chi_square_reduced", "Reduced chi-squared", True),
        ("model_fit_snr", "Model fit SNR", True),
        ("tess_mag", "TESS magnitude", False),
        ("effective_temp", "Effective temp (K)", False),
    ]:
        if col in df.columns:
            hists += _histogram_svg(df[col], title, log_x=logx)

    # co-occurrence over the gating flags (diagnostic + combined catalog)
    cooc_cols = present_diag + (["flag_catalog_eb"] if "flag_catalog_eb" in df.columns else [])
    cooc = _cooccurrence_table(df, cooc_cols)

    # SURVIVOR SECTION -- this is the security boundary.
    # For the public view we do NOT call _survivor_table at all, so the embedded
    # survivor JSON is never generated and cannot leak. We emit a request-access
    # panel in its place. For full/private, the survivor table (with data) renders.
    if is_public:
        survivors = _request_access_panel(n_survivors)
        survivor_heading = "Preliminary results (survivor candidates)"
        exominer_section = _exominer_section(df, scores, public=True)
    else:
        survivors = _survivor_table(df, scores)
        survivor_heading = "Unflagged survivors"
        exominer_section = _exominer_section(df, scores)

    # The survivor-table filtering JS is only meaningful when the survivor table
    # exists. For the public build we emit NOTHING here -- no survivor-related
    # script at all -- so the public artifact carries zero survivor machinery.
    survivor_filter_script = "" if is_public else _SURVIVOR_FILTER_JS

    n_tics = df["tic_id"].nunique() if "tic_id" in df.columns else 0
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    sectors = _sector_str(df)
    # data-version stamp: a live dashboard is re-published per processing run, so
    # viewers need to know which run they're seeing.
    data_version = ""
    if "tce_sample_version" in df.columns and df["tce_sample_version"].notna().any():
        data_version = str(df["tce_sample_version"].dropna().iloc[0])
    _view_label = {
        "public": "Public view — summary only; survivor candidate list available on request.",
        "private": "Private view — for collaborators and sponsors. Contains preliminary survivor candidates.",
        "full": "Full internal view.",
    }.get(view, "Full internal view.")
    view_banner = (
        _view_label
        + (f" Data version: {html.escape(data_version)}." if data_version else "")
        + f" Sectors processed: {html.escape(sectors)}."
    )
    meta_note = (
        "thresholds from sample metadata"
        if thresholds
        else "thresholds unavailable (older parquet); labels show no cutoffs"
    )

    return (
        f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{"MegaMiner — public summary" if is_public else "TCE sample report"}</title>
<style>
  /* Design tokens matched to the technosurveys.com site (dark theme, Inter). */
  :root {{
    color-scheme: dark;
    --bg:#0d0f0d; --bg-soft:#151813; --ink:#f4f0e6; --muted:#b8b2a4;
    --line:rgba(244,240,230,0.16); --line-strong:rgba(244,240,230,0.28);
    --green:#60d39f; --coral:#f2745f; --amber:#e9c85c; --violet:#9aa2ff; --cyan:#61d8e4;
    --panel:rgba(21,24,19,0.82); --panel-strong:rgba(29,33,26,0.94);
    --radius:8px;
  }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          color:var(--ink); background:var(--bg); margin:0; padding:32px; line-height:1.55; }}
  h1 {{ font-size:clamp(1.8rem,3vw,2.4rem); font-weight:800; letter-spacing:0; line-height:1.05; margin:0 0 6px; }}
  h2 {{ font-size:0.86rem; font-weight:900; letter-spacing:0.12em; text-transform:uppercase;
        color:var(--muted); margin:40px 0 10px; border-bottom:1px solid var(--line); padding-bottom:8px; }}
  .sub {{ color:var(--muted); font-size:14px; margin:0 0 8px; }}
  .secsub {{ color:var(--muted); font-size:13px; margin:0 0 10px; }}
  .stats {{ display:flex; gap:14px; flex-wrap:wrap; margin:18px 0; }}
  .stat {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:14px 20px; min-width:130px; }}
  .stat .big {{ font-size:30px; font-weight:800; color:var(--green); }}
  .stat .lbl {{ font-size:12px; color:var(--muted); }}
  .row {{ display:flex; align-items:center; gap:10px; margin:5px 0; }}
  .rlabel {{ width:340px; font-size:13px; text-align:right; flex:none; }}
  .track {{ flex:1 1 auto; min-width:80px; background:rgba(244,240,230,0.08); border-radius:5px; height:20px; overflow:hidden; }}
  .fill {{ height:100%; border-radius:5px; }}
  .rval {{ width:170px; font-size:13px; flex:none; white-space:nowrap; }}
  .pct {{ color:var(--muted); }}
  .hists {{ display:flex; flex-wrap:wrap; gap:20px; }}
  .hist {{ background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); padding:12px 14px; }}
  .htitle {{ font-size:14px; font-weight:700; margin-bottom:6px; }}
  .histsvg {{ width:560px; height:300px; max-width:100%; }}
  .tick {{ font-size:11px; fill:var(--muted); }}
  .axislabel {{ font-size:11px; fill:var(--muted); }}
  .hsub {{ font-size:12px; color:var(--muted); margin-top:4px; }}
  .empty {{ color:var(--muted); font-style:italic; }}
  .reqaccess {{ background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--green); border-radius:var(--radius); padding:18px 22px; max-width:760px; }}
  .reqlead {{ font-size:14px; margin:0 0 12px; }}
  .reqbtn {{ display:inline-flex; align-items:center; min-height:46px; background:var(--green); color:#0d0f0d; text-decoration:none; font-weight:800; font-size:14px; padding:0 18px; border-radius:var(--radius); transition:transform 160ms ease, background 160ms ease; }}
  .reqbtn:hover {{ transform:translateY(-1px); background:#7ae0b3; }}
  .reqnote {{ font-size:12px; color:var(--muted); margin:12px 0 0; }}
  .viewbanner {{ font-size:12px; color:var(--muted); margin:2px 0 0; }}
  table.cooc {{ border-collapse:collapse; font-size:12px; }}
  table.cooc td, table.cooc th {{ border:1px solid var(--line); padding:4px 7px; text-align:center; }}
  table.cooc th.rot {{ height:90px; white-space:nowrap; }}
  table.cooc th.rot div {{ transform:rotate(-60deg); width:20px; }}
  table.cooc th.rowlab {{ text-align:right; font-weight:600; }}
  table.cooc td.diag {{ font-weight:700; background:rgba(96,211,159,0.14); }}
  table.survivors {{ border-collapse:collapse; font-size:12px; width:100%; }}
  table.survivors th, table.survivors td {{ border:1px solid var(--line); padding:4px 8px; text-align:right; }}
  table.survivors th {{ background:var(--panel-strong); cursor:pointer; position:sticky; top:0; }}
  table.survivors tbody tr:nth-child(even) {{ background:rgba(244,240,230,0.03); }}
  table.survivors th.exocol {{ background:rgba(154,162,255,0.16); }}
  .filters {{ display:flex; flex-wrap:wrap; gap:8px 14px; margin:10px 0; padding:12px;
             background:var(--bg-soft); border:1px solid var(--line); border-radius:var(--radius); }}
  .frow {{ display:flex; align-items:center; gap:5px; }}
  .flabel {{ font-size:11px; color:var(--muted); font-family:ui-monospace,monospace; white-space:nowrap; }}
  .finput {{ width:120px; padding:3px 6px; font-size:12px; border:1px solid var(--line-strong); border-radius:4px; background:var(--bg-soft); color:var(--ink); }}
  .frange {{ width:74px; padding:3px 5px; font-size:12px; border:1px solid var(--line-strong); border-radius:4px; background:var(--bg-soft); color:var(--ink); }}
  .fselect, .ftoggle {{ padding:3px 5px; font-size:12px; border:1px solid var(--line-strong); border-radius:4px; background:var(--bg-soft); color:var(--ink); }}
  .fdash {{ font-size:10px; color:var(--muted); }}
  .survbar {{ display:flex; justify-content:space-between; align-items:center; margin:8px 0; flex-wrap:wrap; gap:8px; }}
  .survcount {{ font-size:13px; color:var(--muted); font-weight:600; }}
  .survbtns {{ display:flex; gap:8px; }}
  .dlbtn {{ padding:6px 12px; font-size:12px; border:1px solid var(--violet); background:rgba(154,162,255,0.16); color:var(--ink);
            border-radius:5px; cursor:pointer; }}
  .dlbtn:hover {{ background:rgba(154,162,255,0.28); }}
  .resetbtn {{ background:var(--bg-soft); color:var(--muted); border-color:var(--line-strong); }}
  .resetbtn:hover {{ background:rgba(244,240,230,0.08); }}
  .survscroll {{ max-height:600px; overflow:auto; border:1px solid var(--line); border-radius:4px; }}
  table.survivors td.exocol {{ background:rgba(154,162,255,0.08); }}
  table.survivors tbody tr:nth-child(even) td.exocol {{ background:rgba(154,162,255,0.12); }}
  .note {{ font-size:12px; color:var(--muted); max-width:860px; }}
</style></head><body>

<h1>{"MegaMiner — Public Summary" if is_public else "TCE sample inspection report"}</h1>
<p class="sub">source: {html.escape(source_name)} &middot; sector(s): {html.escape(sectors)} &middot; generated {generated} &middot; {meta_note}</p>
<p class="viewbanner">{view_banner}</p>

<div class="stats">
  <div class="stat"><div class="big">{n_total:,}</div><div class="lbl">TCEs</div></div>
  <div class="stat"><div class="big">{n_tics:,}</div><div class="lbl">unique TICs</div></div>
  <div class="stat"><div class="big">{n_clean:,}</div><div class="lbl">in clean sample</div></div>
  <div class="stat"><div class="big">{n_unflag_diag:,}</div><div class="lbl">unflagged by diagnostics</div></div>
  <div class="stat"><div class="big">{n_unflag_cat:,}</div><div class="lbl">unflagged by vetted catalogs</div></div>
  <div class="stat"><div class="big">{n_survivors:,}</div><div class="lbl">unflagged survivors</div></div>
</div>

<h2>Summary</h2>
{summary}
{summary_note}

<h2>Gaia Stellar Parameters</h2>
<p class="secsub">Host-star parameters from the <a href="https://doi.org/10.1093/mnras/stae616" target="_blank" rel="noopener noreferrer">Doyle et al. (2024)</a> TESS&ndash;Gaia cross-match. Parameter cuts (True = passed) are informational; these do not gate.</p>
{gaia_xmatch_bar}
{cut_bars or "<p class='empty'>No stellar-cut columns.</p>"}

<h2>Diagnostic flags</h2>
<p class="secsub">DV signal-quality diagnostics (True = suspicious). These gate survivors.</p>
{diag_bars or "<p class='empty'>No diagnostic-flag columns.</p>"}

<h2>Catalog flags</h2>
<p class="secsub">Vetted eclipsing-binary catalogs (True = known EB). Vetted membership gates; unvetted is annotation only.</p>
{cat_bars or "<p class='empty'>No catalog-flag columns.</p>"}
{cat_annot_bar}

<h2>Distributions</h2>
<div class="hists">{hists or "<p class='empty'>No distribution columns.</p>"}</div>

<h2>Flag co-occurrence</h2>
{cooc}

{exominer_section}

<h2>{survivor_heading}</h2>
{survivors}
"""
        + survivor_filter_script
        + """
</body></html>"""
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Generate an HTML report from a TCE sample.")
    ap.add_argument("input", type=Path, help="Path to tce_sample_v1.parquet (or .csv)")
    ap.add_argument("-o", "--output", type=Path, default=None, help="Output HTML path")
    ap.add_argument(
        "--scores",
        type=Path,
        default=None,
        help="Optional scored-survivors parquet (ExoMiner). Adds an ExoMiner scores section.",
    )
    ap.add_argument(
        "--view",
        choices=["full", "private", "public"],
        default="full",
        help=(
            "Which build to generate. 'full'/'private' include the survivor table "
            "(and its embedded data). 'public' OMITS the survivor data entirely "
            "(summary only + request-access panel) -- the security boundary for "
            "the public dashboard."
        ),
    )
    args = ap.parse_args(argv)
    if not args.input.is_file():
        print(f"ERROR: input not found: {args.input}")
        return 1
    df = _read(args.input)
    if df.empty:
        print("ERROR: input has no rows.")
        return 1
    scores = None
    if args.scores is not None:
        if not args.scores.is_file():
            print(f"WARNING: scores file not found, skipping: {args.scores}")
        else:
            scores = _read(args.scores)
    thresholds = _read_thresholds(args.input) if args.input.suffix != ".csv" else {}
    out = args.output or args.input.with_name(args.input.stem + f"_dashboard_{args.view}.html")
    out.write_text(
        build_report(df, args.input.name, thresholds, scores, view=args.view), encoding="utf-8"
    )
    n_scored = f", {len(scores):,} scored" if scores is not None else ""
    print(f"wrote {out}  [{args.view} view]  ({len(df):,} TCEs{n_scored})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
