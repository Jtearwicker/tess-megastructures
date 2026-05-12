# Vetting protocol v1 (draft)

Status: **DRAFT** — finalize before main vetting begins. Update via PR
with advisor review.

This document specifies how candidates are classified during human review.
It is normative for v1 and is cited in the v1 paper as the methodology.

## Purpose

For a defensible candidate count in the v1 paper, classification must be:

- **Reproducible:** another vetter following these rules should reach
  similar classifications.
- **Documented:** decision criteria written down before vetting starts.
- **Auditable:** every classification recorded with vetter, date, and
  package version.

## Process

1. **Calibration round (~30 candidates).** Vet a small set, then have
   the advisor independently vet the same set. Compare. Update this
   protocol with examples and edge-case rules. Repeat until classifications
   agree on >80% of candidates.
2. **Main round.** Vet the full queue. Each candidate gets one initial
   classification.
3. **Re-vetting round.** Anything classified `unsure`, `unexplained_interesting`,
   or `megastructure_candidate` gets a second pass after a break of at
   least one week, and ideally a second vetter.
4. **Follow-up triage.** Candidates surviving re-vetting get archival
   photometry and (if available) spectroscopic follow-up.

## Classification taxonomy

A candidate is assigned exactly one classification per (vetter, round).

### `planet`

The signal is consistent with a transiting exoplanet. No anomalous
features beyond what's expected for the planet hypothesis. Confidence:
typically high if the DV report shows a clean U-shaped transit, no
secondary eclipse, no centroid offset.

### `eb_missed`

The signal is an eclipsing binary that the filter chain didn't catch.
Indicators: V-shaped transit, secondary eclipse visible in the
weak-secondary plot, ellipsoidal variations, depth >>10%. SIMBAD or
catalog confirmation supports but isn't required.

### `instrumental`

The signal is a systematic, not astrophysical. Indicators: dips
correlated with TESS momentum dumps, scattered light events, sector
boundaries; signal disappears in alternative apertures.

### `background`

Signal originates from a nearby blended source, not the target.
Indicators: centroid offset visible in DV report (even if below 3σ),
nearby bright source visible in the difference image, signal stronger
in halo than core (despite the ghost diagnostic threshold).

### `known_variable`

Signal is explained by stellar variability of a recognized type.
Indicators: SIMBAD classification consistent with the light curve
behavior, stellar parameters in a known variable region of the HR
diagram (e.g., delta Sct strip), variability amplitude matching
class expectations.

### `unexplained_uninteresting`

Signal doesn't fit a standard explanation, but doesn't show features
that match any Wright+16 megastructure signature either. Examples:
shallow noise-like dips with no clear model fit, single-event signals
where re-observation didn't recover them. Document why the signal is
"uninteresting" in notes.

### `unexplained_interesting`

Signal is anomalous and worth follow-up but doesn't specifically match
a megastructure signature. Could be a new astrophysical phenomenon,
a poorly-understood object class, or an outlier in known classes.
These feed the "serendipitous discoveries" section of the v1 paper.

### `megastructure_candidate`

Signal exhibits one or more Wright+16 signature features:

- W1: anomalous depth-duration ratio (e.g., very deep but planet-like
  duration → very low density → unphysical).
- W2: asymmetric transit profile (Arnold-style non-circular silhouette).
- W3: depth varies between transits (Arnold beacon, KIC 1255-like dust).
- W4: non-Keplerian timing variations not explained by a perturber.
- W5: spectrally flat absorption (wavelength-independent — "manufactured").
- W6: unusual orbital configuration (e.g., resonant chains, circumbinary
  with anomalous geometry).
- W7: aperiodic dimming (deferred to v3).
- W8: very long-period transits with anomalous depth.
- W9: ingress/egress mismatch (suggests rotating non-symmetric body).
- W10: sub-transit-duration features (suggests sub-structure).

Record which signature(s) are matched in the `wright16_match` field.

### `unsure`

Genuinely cannot decide given current information. Triggers automatic
re-vetting. If still unsure after two rounds, escalate to advisor.

## Confidence levels

Each classification carries a confidence: `low` / `medium` / `high`.
Use `low` liberally; revising a confidence is cheap, mis-stating one
is misleading.

## What goes in the `notes` field

Free-text. Intent: capture anything that influenced the decision but
isn't in the structured fields. Examples:

- "Centroid offset suspicious but below threshold; check archival photometry."
- "Period matches a 4-day window in ZTF; verify."
- "Looks like KIC 1255b morphology — flag for v3."
- "Disagree with `simbad_is_variable` flag; SIMBAD entry is from outdated source."

## What does NOT go in this taxonomy

- Vetter's overall opinion of the candidate's "interestingness."
  Use the structured classifications.
- Speculation about specific megastructure designs. Use signature
  matching (W1-W10), not "this looks like a Dyson swarm."

## Open issues

- TODO: collect example TICs for each class as they are vetted.
- TODO: define escalation procedure for advisor review.
- TODO: pre-registration timing (before main vetting? after calibration?).
