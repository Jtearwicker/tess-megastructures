"""End-to-end smoke test on a tiny synthetic dataset.

Runs subsystems A->B->C on a hand-crafted input of ~10 TCEs to verify
that the stages compose correctly and the outputs have the expected
schema. Not a correctness test (those live in stage-specific files);
this is a "the pipeline runs" check.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Implement after subsystems A and B have real code")
def test_pipeline_runs_end_to_end(tmp_path):
    """Running ingest -> annotate -> select-candidates produces a non-empty queue."""
    pass
