"""Subsystem D: Statistical inference (v2).

Not implemented in v1. This namespace is reserved for v2 code that
will combine candidate counts (from :mod:`tess_megastructures.vet`)
with detection efficiency (from :mod:`tess_megastructures.inject`)
to produce upper limits on megastructure occurrence rates as a
function of signal properties.

Planned modules (v2):

- ``efficiency.py``: load and interpolate the eta(theta) table from
  the injection-recovery system.
- ``completeness.py``: parent-sample completeness corrections.
- ``upper_limits.py``: Poisson upper limits and posteriors.
- ``sensitivity_maps.py``: 2D sensitivity figures for the paper.
"""
