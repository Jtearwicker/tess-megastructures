"""tess_megastructures: A pipeline for identifying anomalous transit signals
in TESS-SPOC Data Validation products.

The package is organized into subsystems matching the architecture document
(``docs/architecture.md``):

- :mod:`tess_megastructures.ingest` — Subsystem A: parent sample and TCE ingest.
- :mod:`tess_megastructures.annotate` — Subsystem B: annotation, filters, scoring.
- :mod:`tess_megastructures.vet` — Subsystem C: candidate selection and vetting log.
- :mod:`tess_megastructures.infer` — Subsystem D: statistical inference (v2).
- :mod:`tess_megastructures.inject` — Injection-recovery (v2).
- :mod:`tess_megastructures.catalogs` — Reference catalog loaders.
"""

__version__ = "0.1.0dev"
