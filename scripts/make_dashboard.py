"""Generate a static HTML inspection report from a TCE sample Parquet.

Reads a tce_sample_v1.parquet (the output of build_tce_sample) and writes a
single self-contained HTML file with no external dependencies: a funnel, the
per-flag breakdown, flag co-occurrence, distributions, and the unflagged
survivor table. Open it in a browser; it works offline and can be emailed.

Usage
-----
    uv run python scripts/make_dashboard.py INPUT.parquet [-o OUTPUT.html]

If -o is omitted, writes alongside the input as <input_stem>_dashboard.html.

This is an inspection tool, not part of the pipeline. It reads only; it never
modifies the sample.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import sys
from pathlib import Path

import pandas as pd

# Human-readable labels for the diagnostic flags.
FLAG_LABELS = {
    "flag_suspected_eb": "Suspected eclipsing binary (SPOC)",
    "flag_no_convergence": "Transit fit did not converge",
    "flag_invalid_odd_even": "Invalid odd/even statistic",
    "flag_background_eb": "Background / blended EB (ghost)",
    "flag_centroid_offset": "Off-target centroid offset",
    "flag_matching_period": "Matching-period signals",
    "flag_large_odd_even": "Large odd/even depth difference",
    "flag_low_snr": "Low S/N",
    "flag_low_rchisq": "Low reduced chi-squared",
}

# Human-readable labels for the stellar cuts.
CUT_LABELS = {
    "passed_tmag_cut": "Tmag in range",
    "passed_log_g_cut": "Surface gravity (log g)",
    "passed_parallax_cut": "Parallax S/N",
    "passed_ruwe_cut": "RUWE (astrometric)",
}


def _flag_label(col: str) -> str:
    return FLAG_LABELS.get(col, col.replace("flag_", "").replace("_", " "))


def _cut_label(col: str) -> str:
    return CUT_LABELS.get(col, col.replace("passed_", "").replace("_", " "))


def _sector_str(df: pd.DataFrame) -> str:
    """Human string of the sector(s) present in the sample."""
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
    """Build the public MAST DV mini-report (dvm.pdf) URL for a TIC + sector.

    Returns None if tic_id or sector is missing/unparseable (e.g. an
    aggregated multi-sector row where the single sector is ambiguous), so the
    caller can omit the link rather than emit a broken URL.
    """
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


# Columns shown in the survivor table, if present.
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
    """Read the sample. Parquet by default; .csv supported for convenience."""
    if path.suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)


def _bool_count(df: pd.DataFrame, col: str) -> int:
    s = df[col]
    return int(s.sum() if s.dtype == "bool" else s.fillna(False).astype(bool).sum())


def _bar(label: str, value: int, total: int, color: str = "#3c7d4e") -> str:
    pct = (value / total * 100) if total else 0
    return f"""
    <div class="row">
      <div class="rlabel">{html.escape(label)}</div>
      <div class="track"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div>
      <div class="rval">{value:,} <span class="pct">({pct:.1f}%)</span></div>
    </div>"""


def _histogram_svg(values: pd.Series, title: str, bins: int = 30, log_x: bool = False) -> str:
    """Inline-SVG histogram with labelled x and y axes.

    log_x bins on a log10 scale (for skewed data) but labels the x-axis with
    real data values, not log10 values.
    """
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

    # Canvas + plot area (room for axes).
    w, h = 560, 300
    ml, mr, mt, mb = 56, 12, 10, 40  # margins: left (y labels), right, top, bottom (x labels)
    pw = w - ml - mr  # plot width
    ph = h - mt - mb  # plot height
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

    # Bars.
    bars = []
    for i, c in enumerate(hist):
        bh = (c / maxc) * ph
        x = ml + i * bw
        y = mt + ph - bh
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(bw - 1, 0.5):.1f}" '
            f'height="{bh:.1f}" fill="#5a8aa8"/>'
        )

    # Axis lines.
    axes = (
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt + ph}" stroke="#9aa7b4" stroke-width="1"/>'
        f'<line x1="{ml}" y1="{mt + ph}" x2="{ml + pw}" y2="{mt + ph}" stroke="#9aa7b4" stroke-width="1"/>'
    )

    # Y-axis ticks (0, mid, max counts).
    yticks = []
    for frac in (0.0, 0.5, 1.0):
        cval = int(round(maxc * frac))
        ty = mt + ph - frac * ph
        yticks.append(
            f'<line x1="{ml - 4}" y1="{ty:.1f}" x2="{ml}" y2="{ty:.1f}" stroke="#9aa7b4" stroke-width="1"/>'
            f'<text x="{ml - 7}" y="{ty + 3:.1f}" text-anchor="end" class="tick">{cval:,}</text>'
        )

    # X-axis ticks: 5 positions across the binned range, labelled with real values.
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
    xaxis_label = (
        f'<text x="{ml + pw / 2:.1f}" y="{h - 2}" text-anchor="middle" '
        f'class="axislabel">value{axis_note}</text>'
    )
    yaxis_label = (
        f'<text x="12" y="{mt + ph / 2:.1f}" text-anchor="middle" class="axislabel" '
        f'transform="rotate(-90 12 {mt + ph / 2:.1f})">count</text>'
    )

    return f"""
    <div class="hist">
      <div class="htitle">{html.escape(title)}</div>
      <svg viewBox="0 0 {w} {h}" class="histsvg">
        {"".join(bars)}
        {axes}
        {"".join(yticks)}
        {"".join(xticks)}
        {xaxis_label}
        {yaxis_label}
      </svg>
      <div class="hsub">n={len(v):,} &middot; median {v.median():,.4g} &middot; range {v.min():,.4g} to {v.max():,.4g}</div>
    </div>"""


def _cooccurrence_table(df: pd.DataFrame, flag_cols: list[str]) -> str:
    """Flag co-occurrence: for each pair, how many TCEs trip BOTH."""
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
                # shade by overlap fraction relative to the diagonal of ci
                base = int(bdf[ci].sum()) or 1
                frac = both / base
                shade = f"background:rgba(90,138,168,{frac:.2f})"
                cells.append(f"<td style='{shade}'>{both:,}</td>")
        rows.append(f"<tr><th class='rowlab'>{html.escape(short[i])}</th>{''.join(cells)}</tr>")
    return f"""
    <table class="cooc">
      <tr><th></th>{header}</tr>
      {"".join(rows)}
    </table>
    <p class="note">Cell = number of TCEs tripping both flags. Row shading is
    relative to the row flag's own total (diagonal). Read across a row to see
    what else its TCEs tend to trip.</p>"""


def _survivor_table(df: pd.DataFrame) -> str:
    unflagged = (
        df[~df["any_diagnostic_flag"].fillna(False).astype(bool)]
        if "any_diagnostic_flag" in df.columns
        else df.iloc[0:0]
    )
    cols = [c for c in SURVIVOR_COLUMNS if c in unflagged.columns]
    if unflagged.empty or not cols:
        return "<p class='empty'>No unflagged survivors (or no displayable columns).</p>"
    can_link = {"tic_id", "sector"}.issubset(unflagged.columns)
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    if can_link:
        head += "<th>DV report</th>"
    body_rows = []
    for _, r in unflagged.iterrows():
        cells = []
        for c in cols:
            val = r[c]
            if isinstance(val, float):
                cells.append(f"<td>{val:,.4g}</td>")
            else:
                cells.append(f"<td>{html.escape(str(val))}</td>")
        if can_link:
            url = mast_dvr_url(r.get("tic_id"), r.get("sector"))
            if url:
                cells.append(
                    f'<td><a href="{html.escape(url)}" target="_blank" '
                    f'rel="noopener noreferrer">PDF</a></td>'
                )
            else:
                cells.append("<td>&mdash;</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
    <table class="survivors" id="survivors">
      <thead><tr>{head}</tr></thead>
      <tbody>{"".join(body_rows)}</tbody>
    </table>
    <p class="note">{len(unflagged):,} unflagged TCEs (tripped no diagnostic).
    Click a column header to sort. "DV report" links open the TESS-SPOC
    Data Validation mini-report (dvm.pdf) on MAST in a new tab.</p>"""


def build_report(df: pd.DataFrame, source_name: str) -> str:
    n_total = len(df)
    flag_cols = [c for c in df.columns if c.startswith("flag_")]
    cut_cols = [c for c in df.columns if c.startswith("passed_")]

    # --- funnel
    n_clean = _bool_count(df, "in_clean_sample") if "in_clean_sample" in df else 0
    n_any = _bool_count(df, "any_diagnostic_flag") if "any_diagnostic_flag" in df else 0
    n_unflagged = n_total - n_any
    funnel = _bar("Total TCEs", n_total, n_total, "#2f6090")
    if "in_clean_sample" in df:
        funnel += _bar("In clean sample (stellar cuts)", n_clean, n_total, "#2f6090")
    funnel += _bar("Unflagged survivors", n_unflagged, n_total, "#3c7d4e")

    # --- per-flag bars (sorted desc)
    flag_counts = sorted(((c, _bool_count(df, c)) for c in flag_cols), key=lambda x: -x[1])
    flag_bars = "".join(_bar(_flag_label(c), n, n_total, "#c0712e") for c, n in flag_counts)

    # --- stellar cut bars
    cut_bars = "".join(_bar(_cut_label(c), _bool_count(df, c), n_total) for c in cut_cols)

    # --- distributions
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

    cooc = _cooccurrence_table(df, flag_cols)
    survivors = _survivor_table(df)

    n_tics = df["tic_id"].nunique() if "tic_id" in df.columns else 0
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    sectors = _sector_str(df)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TCE sample report</title>
<style>
  :root {{ --ink:#1b2a38; --muted:#5a6b7b; --line:#dce4ec; --bg:#f7f9fb; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif; color:var(--ink);
    background:var(--bg); margin:0; padding:32px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }}
  h2 {{ font-size:18px; margin:32px 0 12px; border-bottom:2px solid var(--line); padding-bottom:6px; }}
  .sub {{ color:var(--muted); font-size:14px; margin:0 0 8px; }}
  .stats {{ display:flex; gap:14px; flex-wrap:wrap; margin:18px 0; }}
  .stat {{ background:#fff; border:1px solid var(--line); border-radius:10px;
    padding:14px 20px; min-width:130px; }}
  .stat .big {{ font-size:30px; font-weight:700; color:#2f6090; }}
  .stat .lbl {{ font-size:12px; color:var(--muted); }}
  .row {{ display:flex; align-items:center; gap:10px; margin:5px 0; }}
  .rlabel {{ width:230px; font-size:13px; text-align:right; flex:none; }}
  .track {{ flex:1 1 auto; min-width:80px; background:#eef1f4; border-radius:5px; height:20px; overflow:hidden; }}
  .fill {{ height:100%; border-radius:5px; }}
  .rval {{ width:120px; font-size:13px; flex:none; white-space:nowrap; }}
  .pct {{ color:var(--muted); }}
  /* In the side-by-side flags/cuts section, columns must be wide enough that
     the bar track survives. Give each column a real basis and shrink the
     label so the track is never squeezed to zero. */
  .twocol {{ display:flex; gap:32px; flex-wrap:wrap; align-items:flex-start; }}
  .twocol > div {{ flex:1 1 540px; min-width:480px; }}
  .twocol .rlabel {{ width:210px; }}
  .twocol .rval {{ width:110px; }}
  .hists {{ display:flex; flex-wrap:wrap; gap:20px; }}
  .hist {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
  .htitle {{ font-size:14px; font-weight:600; margin-bottom:6px; }}
  .histsvg {{ width:560px; height:300px; max-width:100%; }}
  .tick {{ font-size:11px; fill:var(--muted); }}
  .axislabel {{ font-size:11px; fill:var(--muted); }}
  .hstats {{ font-size:11px; color:var(--ink); margin-top:2px; }}
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
  .note {{ font-size:12px; color:var(--muted); max-width:760px; }}
</style></head><body>

<h1>TCE sample inspection report</h1>
<p class="sub">source: {html.escape(source_name)} &middot; sector(s): {html.escape(sectors)} &middot; generated {generated}</p>

<div class="stats">
  <div class="stat"><div class="big">{n_total:,}</div><div class="lbl">TCEs</div></div>
  <div class="stat"><div class="big">{n_tics:,}</div><div class="lbl">unique TICs</div></div>
  <div class="stat"><div class="big">{n_clean:,}</div><div class="lbl">in clean sample</div></div>
  <div class="stat"><div class="big">{n_unflagged:,}</div><div class="lbl">unflagged survivors</div></div>
</div>

<h2>Funnel</h2>
{funnel}

<div class="twocol">
  <div>
    <h2>Diagnostic flags (True = suspicious)</h2>
    {flag_bars or "<p class='empty'>No flag columns.</p>"}
  </div>
  <div>
    <h2>Stellar cuts (True = passed)</h2>
    {cut_bars or "<p class='empty'>No cut columns.</p>"}
  </div>
</div>

<h2>Distributions</h2>
<div class="hists">{hists or "<p class='empty'>No distribution columns.</p>"}</div>

<h2>Flag co-occurrence</h2>
{cooc}

<h2>Unflagged survivors</h2>
{survivors}

<script>
// Click-to-sort for the survivor table.
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

    out = args.output or args.input.with_name(args.input.stem + "_dashboard.html")
    html_text = build_report(df, args.input.name)
    out.write_text(html_text, encoding="utf-8")
    print(f"wrote {out}  ({len(df):,} TCEs)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
