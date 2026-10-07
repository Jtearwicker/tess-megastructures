"""B6: Anomaly score for vetting prioritization.

The score is a numeric ranking, not a classifier. It exists to order
the candidates so vetting attention goes to the most promising first.
It is computed for ALL TCEs (flags-not-cuts): nothing is dropped.

v1 score:
    score = w_chisq * log10(reduced_chisq)
          + w_odd_even * log10(odd_even_sig / odd_even_threshold)
          + w_snr * log10(model_fit_snr)

Weights and reference values come from ``score_config_v1.yaml``.

METRIC SANITY
-------------
A small number of TCEs (~0.05%) carry corrupted DV metric values --
reduced chi-squares up to 1e24, signal-to-noise ratios up to 1e11 --
which would otherwise dominate the ranking with numerical artifacts
rather than real anomalies. We distinguish *corruption* from *extremity*:

- An extreme reduced-chisq from a CONVERGED fit with a sane SNR is a
  real (if unusual) anomaly -- exactly what the search is for. Kept
  uncapped so it ranks high.
- An extreme metric from a NON-CONVERGED fit, or alongside an impossible
  SNR, is a broken value. It is winsorized for scoring (so it can't
  dominate) and flagged ``flag_implausible_metrics``.

Raw metric columns are never modified; winsorization affects only the
score. All rows are retained and labelled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RCHISQ_COL = "model_chi_square_reduced"
ODD_EVEN_COL = "odd_even_depth_sig"
SNR_COL = "model_fit_snr"

# Sanity ceilings (physical, for TESS-SPOC DV metrics).
SNR_CEILING = 1e4        # real TESS SNRs are <~ few thousand; >1e4 is corrupt
SNR_FLOOR = 0.01         # a "detected" TCE with ~0 SNR is a broken value
RCHISQ_CEILING = 1e4     # cap applied ONLY to corruption-flagged rows


def _safe_log10(s: pd.Series) -> pd.Series:
    vals = pd.to_numeric(s, errors="coerce")
    out = pd.Series(np.nan, index=s.index, dtype="float64")
    positive = vals > 0
    out[positive] = np.log10(vals[positive])
    return out


def compute_anomaly_score(tces: pd.DataFrame, score_config: dict) -> pd.DataFrame:
    """Add ``anomaly_score`` (+ components + ``flag_implausible_metrics``).

    Computed for ALL rows. Corrupted-metric rows are flagged and their
    corrupted metric winsorized for scoring; genuine extreme anomalies are
    left uncapped.
    """
    weights = score_config.get("weights", {})
    w_chisq = float(weights.get("chisq", 1.0))
    w_odd_even = float(weights.get("odd_even", 0.3))
    w_snr = float(weights.get("snr", 0.5))
    oe_threshold = float(
        score_config.get("reference", {}).get("odd_even_threshold", 35.0)
    )

    out = tces.copy()

    snr = pd.to_numeric(out.get(SNR_COL), errors="coerce") if SNR_COL in out else pd.Series(np.nan, index=out.index)
    rchisq = pd.to_numeric(out.get(RCHISQ_COL), errors="coerce") if RCHISQ_COL in out else pd.Series(np.nan, index=out.index)
    noconv = out["flag_no_convergence"].fillna(False).astype(bool) if "flag_no_convergence" in out else pd.Series(False, index=out.index)

    # --- corruption detection -------------------------------------------------
    # A reduced chi-square above the ceiling is physically implausible on its
    # face -- a value of 1e4+ means residuals ~100x the error bars, which is a
    # broken metric, not a real object. Convergence does NOT rescue it (many
    # such values come from converged fits). The clean population tops out near
    # ~1e3 (99.9th pct of converged/sane-SNR TCEs = 774), so 1e4 keeps the real
    # bad-fit tail while flagging the ~124 clear artifacts.
    implausible_snr = (snr > SNR_CEILING) | (snr < SNR_FLOOR)
    corrupt_chisq = rchisq > RCHISQ_CEILING
    out["flag_implausible_metrics"] = (implausible_snr | corrupt_chisq).fillna(False)

    # --- score components ----------------------------------------------------
    # A corrupted metric carries NO anomaly information, so its component is
    # EXCLUDED (set NaN -> skipped in the sum), not capped. Capping would peg
    # a broken TCE to the ceiling ("maximally anomalous"), which is wrong; a
    # meaningless value should neither dominate nor rank high. The row is
    # retained and labelled ``flag_implausible_metrics`` for inspection.
    snr_for_score = snr.where(~implausible_snr, np.nan)
    rchisq_for_score = rchisq.where(~corrupt_chisq, np.nan)

    comp_chisq = _safe_log10(rchisq_for_score)
    comp_oe = (
        _safe_log10(pd.to_numeric(out[ODD_EVEN_COL], errors="coerce") / oe_threshold)
        if ODD_EVEN_COL in out else pd.Series(np.nan, index=out.index)
    )
    comp_snr = _safe_log10(snr_for_score)

    out["score_chisq"] = w_chisq * comp_chisq
    out["score_odd_even"] = w_odd_even * comp_oe
    out["score_snr"] = w_snr * comp_snr

    comps = out[["score_chisq", "score_odd_even", "score_snr"]]
    out["anomaly_score"] = comps.sum(axis=1, skipna=True)
    out.loc[comps.isna().all(axis=1), "anomaly_score"] = np.nan

    return out
