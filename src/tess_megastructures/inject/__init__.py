"""Injection-recovery system (v2).

Not implemented in v1. This namespace is reserved for v2 code that
characterizes the pipeline's detection efficiency by injecting
synthetic megastructure-like signals into FFI light curves and
measuring what fraction are recovered as TCEs and survive the
filter chain.

Planned modules (v2):

- ``signal_models.py``: parameterized Wright+16 signature classes
  (asymmetric transits, depth-varying transits, etc.).
- ``inject.py``: insert synthetic signals into FFI light curves.
- ``recover.py``: run the equivalent of SPOC's TPS+DV on injected
  light curves (or a documented proxy).
- ``efficiency_table.py``: build the eta(theta, stellar_params) table.
"""
