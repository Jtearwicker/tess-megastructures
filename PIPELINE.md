# MegaMiner pipeline structure

This document states the working-set definition and the EB-handling structure the
pipeline uses, and records the calibration that sets the one tunable threshold.
It is the reference for how signals are removed, hidden, ranked, and annotated.

## Goal

MegaMiner searches TESS for transit-like signals that do not look like ordinary
planets, as candidates for megastructures and other unusual astrophysics. The
search surfaces un-planet-like light curves. The dominant contaminant at the top
of the ranking is the eclipsing binary, because a planet model fits a deep stellar
eclipse badly and so scores high. Most of the pipeline's EB handling exists to
manage that contaminant without discarding genuine anomalies.

## The central tension

`anomaly_score` and the diagnostic flags measure the same property with opposite
sign. The score is high when a signal fits a planet model badly. The diagnostic
flags fire on the same conditions: large odd-even difference, secondary eclipse,
centroid offset, non-convergence. The highest-scoring signals are therefore almost
always flagged, and about 90 percent of all signals carry at least one diagnostic
flag. Gating the search on "no diagnostic flag" would keep the most planet-like,
lowest-scoring corner of the data and discard the anomalies the search exists to
find. Diagnostic flags must annotate and filter, never cut.

## Division of labor

- `anomaly_score` orders signals by how un-planet-like they are. It ranks; it does
  not classify. It cannot separate a megastructure from an eclipsing binary,
  because both fit a planet model badly.
- Catalog EB flags identify known eclipsing binaries. A catalogued EB is a
  confirmed boring object, so this is the only place a hard removal is safe.
- The weak-secondary statistic is a positive physical detection of a secondary
  eclipse, that is, of a second star. It fires on binaries and, at a calibrated
  threshold, does not fire on confirmed planets. This is the one diagnostic that is
  safe to filter on.
- The remaining EB tests (odd-even, ghost diagnostic, radius ratio) and the SPOC
  suspected-EB flag are informative but hide confirmed planets at any useful
  threshold. They annotate and down-rank; they do not cut.
- ExoMiner and the EB-rejection CNN are the real discriminators between
  astrophysical false positives and genuine candidates. They annotate and will
  supersede the hand-built `eb_likelihood`. A classifier can confidently reject a
  true anomaly that lies outside its training distribution, so classifier verdicts
  set an EB-likelihood column and never remove a row.
- DV reports and human vetting are the final judgment. Human vetting is the current
  last step and will be replaced by agentic LLM vetting.

## The structure

The pipeline applies exactly one hard cut, one reversible filter, a ranking, and a
set of annotations. Nothing else removes a signal.

### Hard cut: catalogued EBs

Signals matched to a vetted EB catalog (Prša, Kostov, Oddo, CALNet, combined as
`flag_catalog_eb`) are removed from the working set in every view. Known TOI false
positives, confirmed planets, and known variables are removed on the same basis
where catalogued. This is the only removal that deletes a signal outright. It takes
the working set from 131,743 collapsed signals to 116,099.

### Reversible filter: layer 1, weak secondary

Layer 1 hides signals with `weak_secondary_robust_statistic >= 7`. This is a
positive secondary-eclipse detection, so the object is a binary. The hide is
reversible and audited. It is applied in the private and public views and only
marked, through a `layer1_hidden` column, in the full internal view, so the hidden
set can be inspected without regenerating anything. Layer 1 hides no confirmed
planet in the calibration set (see below) and catches about a quarter of
catalogued EBs outright as a first sieve. What it does not catch still flows to the
classifiers.

### Ranking: anomaly_score

The working set is ordered by `anomaly_score`, highest first. This is the primary
and only ranking. There is no composite priority score yet, deliberately, because
the CNN is meant to become the discriminator and a tuned weighting would be thrown
out when it lands.

### Annotations that never cut

`eb_likelihood` is a transparent 0 to 1 annotation built from the EB tests that are
not safe to filter on (odd-even, ghost, radius ratio) plus the SPOC suspected-EB
flag. It orders within the visible set and hides nothing. ExoMiner scores and, in
future, CNN scores are additional annotations. All of these filter and sort; none
removes a row.

### Reliability axis

Data-quality flags (implausible metrics, corruption, marginal SNR,
non-convergence) sit on a separate axis. They tag a signal as needing review and
set vetting priority. They never remove a signal and never enter the EB decision. A
non-converged high-SNR signal is retained and is arguably more interesting than a
clean one, because no single period fits it.

## Layer-1 calibration

The threshold was set against TFOPWG dispositions from the NASA Exoplanet Archive
TOI table, joined to the working set on TIC id. The join gives 436 confirmed or
known planet hosts (CP/KP) and 522 known false positives (FP/FA). The confirmed
planets are the "must not hide" set and give the false-hide floor.

Each candidate test was swept and read on four numbers: how many catalogued EBs it
catches, how many confirmed planets it would hide (as a count, not only a rate,
because at this sample size a single planet swings the rate), how many known false
positives it catches, and how much of the unlabeled remainder it moves.

Results:

- `weak_secondary_robust_statistic >= 7` hides zero confirmed planets and catches
  24.5 percent of catalogued EBs. The zero holds at 7, 10, and 15. This is the
  layer-1 filter.
- Radius ratio and the SPOC suspected-EB flag each buy a little more EB catch only
  by hiding a real planet. The two planets an OR of these terms would hide are
  TOI-1690 (a short-period grazing planet on a small star) and TOI-6508. Both are
  objects the floor exists to protect. These terms were rejected as filters and
  moved to `eb_likelihood`.
- Odd-even (`odd_even_depth_sig`) requires a threshold near 20 before its planet
  false-hide becomes tolerable, and even there it catches little. Down-rank only.
- The ghost diagnostic points the wrong way: its confirmed-planet median is higher
  than its EB median, and at every threshold it hides more confirmed planets than
  it catches EBs. Down-rank only, or drop.
- `flag_matching_period` hides 45 percent of confirmed planets. It is never a cut.

Note on the metric being the wrong one: the collapsed parquet has both
`odd_even_depth_significance` (near zero, catches nothing, dead) and
`odd_even_depth_sig` (the usable measure). Use the latter.

Two honest limits. First, the floor is "hides no known confirmed planet in our
overlap," on 436 TIC-level hosts. It is not a guarantee for the general case, which
is why layer 1 stays a reversible audited hide rather than a hard cut. Second, the
risk the search actually cares about is the genuine anomaly that has never been
catalogued and would score high. We have no labels for that population, so we
cannot measure a false-hide rate on it. Weak secondary is the safest available
filter against that risk, because a true secondary eclipse is a positive detection
of a second star rather than an inference from a bad fit, but the limit stands and
is the reason the CNN is the real discriminator.

## Implementation

The dashboard (`scripts/make_dashboard_multisector.py`) is the current point of
control. It applies the catalog cut and layer 1, adds `eb_likelihood`, and renders
per view. The layer-1 mask prefers a canonical `flag_weak_secondary_eb` column if
the annotate stage provides one and otherwise thresholds the raw statistic, so the
canonical column can be added later with no dashboard change. The threshold lives
in `LAYER1_WSEC_THRESHOLD`.

The recommended follow-up is to compute `flag_weak_secondary_eb` in the annotate
stage so the filter is a first-class column everywhere, carried through collapse
alongside the other flags. Until the pipeline is next rerun, the dashboard fallback
produces identical results from the existing statistic.
