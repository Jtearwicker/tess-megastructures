"""Streamlit vetting interface.

Run with:

    uv run streamlit run apps/vetting_app/app.py

The app loads the vetting queue from disk, renders the per-candidate
package, and writes classifications to the SQLite vetting log via
:mod:`tess_megastructures.vet.log`.

Design goals:

- Keyboard-shortcut classification (vetting throughput is the bottleneck).
- Pause/resume across sessions: the app remembers where you left off.
- Re-vetting support: revisit any previously classified candidate.
- Progress indicator: see how many candidates remain.

To be implemented during the v1 vetting-prep stage.
"""

from __future__ import annotations


def main() -> None:
    """Entry point. Renders the Streamlit app."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
