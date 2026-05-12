"""Logging configuration for the pipeline.

Pipeline stages use the standard library ``logging`` module rather than
print statements. The convention is:

- Stage entry/exit: INFO
- Per-file errors during parsing: WARNING (don't crash the run)
- Configuration values used: DEBUG
- Unrecoverable errors: ERROR (which then raises)

Logs are written to both stderr and a per-stage log file under
``paths.log_dir``.
"""

from __future__ import annotations

import logging
from pathlib import Path


def get_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    """Get a configured logger.

    Parameters
    ----------
    name : str
        Logger name, conventionally the module's ``__name__``.
    log_dir : Path, optional
        If provided, attach a FileHandler that writes to ``<log_dir>/<name>.log``.

    Returns
    -------
    logging.Logger
    """
    raise NotImplementedError("To be implemented during repo scaffolding step.")
