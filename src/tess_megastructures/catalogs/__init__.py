"""Reference catalog loaders.

Each module loads one published catalog and returns a tidy DataFrame
with a ``ticId`` column suitable for cross-matching against the master
TCE table. Catalog file paths and metadata come from
``configs/catalogs.yaml``.

These loaders replace the existing ``binary_catalogs.py``, separating
each catalog into its own module for clarity and easier updates when
new versions are published.
"""
