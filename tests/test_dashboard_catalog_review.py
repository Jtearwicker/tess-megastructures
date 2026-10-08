"""Catalog review information stays private in dashboard builds."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _dashboard_module():
    path = Path(__file__).parents[1] / "scripts" / "make_dashboard_multisector.py"
    spec = importlib.util.spec_from_file_location("make_dashboard_multisector", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_catalog_routes_render_private_but_not_public():
    dashboard = _dashboard_module()
    frame = pd.DataFrame(
        [
            {
                "tic_id": 123,
                "planet_number": 1,
                "sector": 36,
                "flag_catalog_eb": False,
                "weak_secondary_robust_statistic": 0.0,
                "anomaly_score": 1.0,
                "catalog_review_route": "review_catalog_context",
                "catalog_route_reason": "position-only VSX match",
                "vsx_types": "YSO",
            }
        ]
    )

    private = dashboard.build_report(frame, "test.parquet", {}, view="private")
    public = dashboard.build_report(frame, "test.parquet", {}, view="public")

    assert "Catalog review routes" in private
    assert "review_catalog_context" in private
    assert "YSO" in private
    assert "Catalog review routes" not in public
    assert "review_catalog_context" not in public
    assert "position-only VSX match" not in public
    assert "YSO" not in public
