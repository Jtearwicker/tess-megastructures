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
    "flag_catalog_eb": "Combined Catalog EBs",
}
CATALOG_FLAG_ORDER = ["flag_prsa_eb", "flag_kostov_eb", "flag_oddo_eb", "flag_catalog_eb"]

# DOI links for each per-source catalog (Combined has no single source).
CATALOG_FLAG_LINKS = {
    "flag_prsa_eb": "https://doi.org/10.3847/1538-4365/ac324a",
    "flag_kostov_eb": "https://doi.org/10.3847/1538-4365/ade2d8",
    "flag_oddo_eb": "https://doi.org/10.3847/1538-4357/ae0c0f",
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
    label: str, value: int, total: int, color: str = "#3c7d4e", label_is_html: bool = False
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
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(bw - 1, 0.5):.1f}" height="{bh:.1f}" fill="#5a8aa8"/>'
        )
    axes = (
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt + ph}" stroke="#9aa7b4" stroke-width="1"/>'
        f'<line x1="{ml}" y1="{mt + ph}" x2="{ml + pw}" y2="{mt + ph}" stroke="#9aa7b4" stroke-width="1"/>'
    )
    yticks = []
    for frac in (0.0, 0.5, 1.0):
        cval = int(round(maxc * frac))
        ty = mt + ph - frac * ph
        yticks.append(
            f'<line x1="{ml - 4}" y1="{ty:.1f}" x2="{ml}" y2="{ty:.1f}" stroke="#9aa7b4" stroke-width="1"/>'
            f'<text x="{ml - 7}" y="{ty + 3:.1f}" text-anchor="end" class="tick">{cval:,}</text>'
        )
    xticks = []
    lo_edge, hi_edge = edges[0], edges[-1]
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        edge_val = lo_edge + frac * (hi_edge - lo_edge)
        real_val = (10**edge_val) if log_x else edge_val
        tx = ml + frac * pw
        xticks.append(
            f'<line x1="{tx:.1f}" y1="{mt + ph}" x2="{tx:.1f}" y2="{mt + ph + 4}" stroke="#9aa7b4" stroke-width="1"/>'
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
                cells.append(f"<td style='background:rgba(90,138,168,{frac:.2f})'>{both:,}</td>")
        rows.append(f"<tr><th class='rowlab'>{html.escape(short[i])}</th>{''.join(cells)}</tr>")
    return f"""
    <table class="cooc"><tr><th></th>{header}</tr>{"".join(rows)}</table>
    <p class="note">Cell = number of TCEs tripping both flags. Row shading is relative to the
    row flag's own total (diagonal).</p>"""


def _survivor_table(df: pd.DataFrame) -> str:
    unflagged = (
        df[~df["any_diagnostic_flag"].fillna(False).astype(bool)]
        if "any_diagnostic_flag" in df.columns
        else df.iloc[0:0]
    )
    cols = [c for c in SURVIVOR_COLUMNS if c in unflagged.columns]
    if unflagged.empty or not cols:
        return "<p class='empty'>No unflagged survivors (or no displayable columns).</p>"
    has_annot = "annotation_kostov_candidate" in unflagged.columns
    can_link = {"tic_id", "sector"}.issubset(unflagged.columns)
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    if has_annot:
        head += "<th>Kostov unvetted</th>"
    if can_link:
        head += "<th>DV report</th>"
    body_rows = []
    for _, r in unflagged.iterrows():
        cells = []
        for c in cols:
            val = r[c]
            cells.append(
                f"<td>{val:,.4g}</td>"
                if isinstance(val, float)
                else f"<td>{html.escape(str(val))}</td>"
            )
        if has_annot:
            is_cand = bool(r.get("annotation_kostov_candidate"))
            cells.append(f"<td>{'yes' if is_cand else '-'}</td>")
        if can_link:
            url = mast_dvr_url(r.get("tic_id"), r.get("sector"))
            if url:
                cells.append(
                    f'<td><a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">PDF</a></td>'
                )
            else:
                cells.append("<td>-</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    note_annot = (
        ' The "Kostov unvetted" column marks TCEs in Kostov\'s unvetted NN '
        "candidate list (annotation only; does not affect survivor status)."
        if has_annot
        else ""
    )
    return f"""
    <table class="survivors" id="survivors">
      <thead><tr>{head}</tr></thead>
      <tbody>{"".join(body_rows)}</tbody>
    </table>
    <p class="note">{len(unflagged):,} unflagged TCEs (no diagnostic and no catalog flag).
    Click a column header to sort. "DV report" links open the TESS-SPOC DV mini-report
    (dvm.pdf) on MAST in a new tab.{note_annot}</p>"""


def build_report(df: pd.DataFrame, source_name: str, thresholds: dict) -> str:
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

    summary = _bar("Total TCEs", n_total, n_total, "#2f6090")
    if "in_clean_sample" in df:
        summary += _bar(
            "In clean sample (stellar cuts, informational)", n_clean, n_total, "#7a8aa0"
        )
    summary += _bar("Unflagged by diagnostic flags", n_unflag_diag, n_total, "#c0712e")
    summary += _bar("Unflagged by catalog flags", n_unflag_cat, n_total, "#8a5a9e")
    summary += _bar("Total unflagged survivors", n_survivors, n_total, "#3c7d4e")

    summary_note = (
        "<p class='note'>Flags are computed independently; each bar is a fraction of all TCEs. "
        "A survivor has no diagnostic flag and no catalog flag. Stellar cuts do not gate.</p>"
    )

    # ---- Stellar cuts (with ranges) ----
    cut_bars = "".join(
        _bar(_cut_label(c, stel), _bool_count(df, c), n_total, "#7a8aa0", label_is_html=True)
        for c in present_cuts
    )

    # ---- Diagnostic flags (with cutoffs) ----
    diag_bars = "".join(
        _bar(_diag_label(c, diag), _bool_count(df, c), n_total, "#c0712e", label_is_html=True)
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
        _bar(_cat_title(c), _bool_count(df, c), n_total, "#8a5a9e", label_is_html=True)
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
        _bar(_annot_title, n_annot, n_total, "#b0a070", label_is_html=True)
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
    survivors = _survivor_table(df)

    n_tics = df["tic_id"].nunique() if "tic_id" in df.columns else 0
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    sectors = _sector_str(df)
    meta_note = (
        "thresholds from sample metadata"
        if thresholds
        else "thresholds unavailable (older parquet); labels show no cutoffs"
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TCE sample report</title>
<style>
  :root {{ --ink:#1b2a38; --muted:#5a6b7b; --line:#dce4ec; --bg:#f7f9fb; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif; color:var(--ink); background:var(--bg); margin:0; padding:32px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }}
  h2 {{ font-size:18px; margin:34px 0 6px; border-bottom:2px solid var(--line); padding-bottom:6px; }}
  .sub {{ color:var(--muted); font-size:14px; margin:0 0 8px; }}
  .secsub {{ color:var(--muted); font-size:13px; margin:0 0 10px; }}
  .stats {{ display:flex; gap:14px; flex-wrap:wrap; margin:18px 0; }}
  .stat {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 20px; min-width:130px; }}
  .stat .big {{ font-size:30px; font-weight:700; color:#2f6090; }}
  .stat .lbl {{ font-size:12px; color:var(--muted); }}
  .row {{ display:flex; align-items:center; gap:10px; margin:5px 0; }}
  .rlabel {{ width:340px; font-size:13px; text-align:right; flex:none; }}
  .track {{ flex:1 1 auto; min-width:80px; background:#eef1f4; border-radius:5px; height:20px; overflow:hidden; }}
  .fill {{ height:100%; border-radius:5px; }}
  .rval {{ width:170px; font-size:13px; flex:none; white-space:nowrap; }}
  .pct {{ color:var(--muted); }}
  .hists {{ display:flex; flex-wrap:wrap; gap:20px; }}
  .hist {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
  .htitle {{ font-size:14px; font-weight:600; margin-bottom:6px; }}
  .histsvg {{ width:560px; height:300px; max-width:100%; }}
  .tick {{ font-size:11px; fill:var(--muted); }}
  .axislabel {{ font-size:11px; fill:var(--muted); }}
  .hsub {{ font-size:12px; color:var(--muted); margin-top:4px; }}
  .empty {{ color:var(--muted); font-style:italic; }}
  table.cooc {{ border-collapse:collapse; font-size:12px; }}
  table.cooc td, table.cooc th {{ border:1px solid var(--line); padding:4px 7px; text-align:center; }}
  table.cooc th.rot {{ height:90px; white-space:nowrap; }}
  table.cooc th.rot div {{ transform:rotate(-60deg); width:20px; }}
  table.cooc th.rowlab {{ text-align:right; font-weight:600; }}
  table.cooc td.diag {{ font-weight:700; background:#e8f0e9; }}
  table.survivors {{ border-collapse:collapse; font-size:12px; width:100%; }}
  table.survivors th, table.survivors td {{ border:1px solid var(--line); padding:4px 8px; text-align:right; }}
  table.survivors th {{ background:#eef1f4; cursor:pointer; position:sticky; top:0; }}
  table.survivors tbody tr:nth-child(even) {{ background:#fafbfc; }}
  .note {{ font-size:12px; color:var(--muted); max-width:860px; }}
</style></head><body>

<h1>TCE sample inspection report</h1>
<p class="sub">source: {html.escape(source_name)} &middot; sector(s): {html.escape(sectors)} &middot; generated {generated} &middot; {meta_note}</p>

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

<h2>Stellar cuts</h2>
<p class="secsub">Host-star property cuts (True = passed). Informational; these do not gate.</p>
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

<h2>Unflagged survivors</h2>
{survivors}

<script>
document.querySelectorAll("table.survivors th").forEach((th, idx) => {{
  th.addEventListener("click", () => {{
    const tbody = th.closest("table").querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr"));
    const asc = !(th.dataset.asc === "true");
    th.dataset.asc = asc;
    rows.sort((a, b) => {{
      const x = a.children[idx].textContent.replace(/,/g, "");
      const y = b.children[idx].textContent.replace(/,/g, "");
      const nx = parseFloat(x), ny = parseFloat(y);
      if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
      return asc ? x.localeCompare(y) : y.localeCompare(x);
    }});
    rows.forEach(r => tbody.appendChild(r));
  }});
}});
</script>
</body></html>"""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Generate an HTML report from a TCE sample.")
    ap.add_argument("input", type=Path, help="Path to tce_sample_v1.parquet (or .csv)")
    ap.add_argument("-o", "--output", type=Path, default=None, help="Output HTML path")
    args = ap.parse_args(argv)
    if not args.input.is_file():
        print(f"ERROR: input not found: {args.input}")
        return 1
    df = _read(args.input)
    if df.empty:
        print("ERROR: input has no rows.")
        return 1
    thresholds = _read_thresholds(args.input) if args.input.suffix != ".csv" else {}
    out = args.output or args.input.with_name(args.input.stem + "_dashboard.html")
    out.write_text(build_report(df, args.input.name, thresholds), encoding="utf-8")
    print(f"wrote {out}  ({len(df):,} TCEs)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
