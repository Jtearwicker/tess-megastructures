# Reading log

A running log of papers consulted, with brief notes on relevance and
key takeaways. Feeds the v1 and v2 paper bibliographies.

Format: bibliographic citation, link, one-paragraph note on what was
useful and where it's used in this project.

---

## Tier 1 — Read first

### Twicken et al. 2018, PASP 130, 064502

**Kepler Data Validation I: Architecture, Diagnostic Tests, and Data
Products for Vetting Transiting Planet Candidates.**

arXiv: https://arxiv.org/abs/1803.04526

Status: TODO read.

Notes: Canonical reference for every diagnostic the parser extracts.
Where used: subsystem A3 (parser), subsystem B5 (filter rationale).

### Li et al. 2019, PASP 131, 024506

**Kepler Data Validation II: Transit Model Fitting and Multiple-planet Search.**

DOI: 10.1088/1538-3873/aaf44d

Status: TODO read.

Notes: Companion to Twicken+18. Covers the transit model fits and
odd/even depth statistic in detail. Where used: subsystem B5.

### Caldwell et al. 2020, RNAAS

**TESS-SPOC FFI Target List Products.**

arXiv: https://arxiv.org/abs/2011.05495

Status: TODO read.

Notes: Defines the TESS-SPOC HLSP product. Target selection criteria,
processing scope. Where used: subsystem A1 (parent sample selection).

### Twicken et al. 2020, EXP-TESS-ARC-ICD-0014 Rev F

**TESS Science Data Products Description Document.**

PDF: https://tasoc.dk/docs/EXP-TESS-ARC-ICD-TM-0014-Rev-F.pdf

Status: Reference (not cover-to-cover).

Notes: Reference manual for what's actually in the XML/FITS files.
Where used: subsystem A3 (parser schema).

### Arnold 2005, ApJ 627, 534

**Transit Light-Curve Signatures of Artificial Objects.**

arXiv: https://arxiv.org/abs/astro-ph/0503580

Status: TODO read.

Notes: Foundational paper for transit-based megastructure searches.
Asymmetric / non-circular silhouettes. Where used: docs/vetting_protocol_v1.md
(W1, W2 signatures).

### Wright et al. 2016, ApJ 816, 17

**The Ĝ Search for ETC IV: Signatures and Information Content of
Transiting Megastructures.**

arXiv: https://arxiv.org/abs/1510.04606

Status: TODO read.

Notes: The conceptual scaffolding. Enumerates 10 signatures.
Where used: docs/vetting_protocol_v1.md (entire W1-W10 taxonomy).

---

## Tier 2 — Megastructure context

### Suazo et al. 2022, MNRAS

**Project Hephaistos I: Upper limits on partial Dyson spheres.**

arXiv: https://arxiv.org/abs/2201.11123

Status: TODO read.

Notes: Different methodology (IR excess, not transits) but the
statistical framework is the model for v2's upper-limit calculation.

### Suazo et al. 2024, MNRAS 531, 695

**Project Hephaistos II: DS candidates from Gaia DR3, 2MASS, WISE.**

arXiv: https://arxiv.org/abs/2405.02927

Status: TODO read.

Notes: Read alongside the Ren+24 contamination critique
(arXiv:2405.14921). Master class in candidate vetting failure modes.

### Boyajian et al. 2016

**Planet Hunters X: KIC 8462852 — Where's the Flux?**

arXiv: https://arxiv.org/abs/1509.03622

Status: TODO read.

Notes: Cautionary tale. Vetting framework that eliminates natural
explanations one by one is the right model.

---

## Tier 3 — Reference catalogs (skim)

### Prša et al. 2022, ApJS 258, 16

**TESS Eclipsing Binary Stars I: 4584 EBs in Sectors 1-26.**

arXiv: https://arxiv.org/abs/2110.13382

Status: skim.

Notes: Source for `binary_catalogs.prsa2022_catalog`.

### Kostov et al. 2025, ApJS

**TESS Ten Thousand Catalog.**

arXiv: https://arxiv.org/abs/2506.05631

Status: skim.

Notes: Source for Tables 3 and 4 cross-matches.

### Doyle et al. 2024, MNRAS 529, 1802

**TESS-SPOC FFI x Gaia.**

arXiv: https://arxiv.org/abs/2403.02407

Status: skim.

Notes: Source for stellar parameters in subsystem A1.

### Bouma et al. 2024, AJ 167, 38

**Transient Corotating Clumps (CPVs) From Four Years of TESS.**

arXiv: https://arxiv.org/abs/2309.06471

Status: skim.

Notes: CPV catalog used in subsystem B3 cross-match.

### Capistrant et al. 2022, ApJS 263, 14

**A Population of Dipper Stars from TESS.**

arXiv: https://arxiv.org/abs/2209.03379

Status: skim.

Notes: Dipper catalog used in subsystem B3 cross-match.

---

## TEMPLATE for new entries

### Author et al. YEAR, Journal vol, page

**Paper title.**

arXiv / DOI: link

Status: TODO read | reading | done | skim.

Notes: Why I read it, what was useful, where it's used in the project.
