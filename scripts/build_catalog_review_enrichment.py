"""Build a pinned CTOI/VSX enrichment table for MegaMiner TCEs.

The CTOI snapshot is a required local input. TIC coordinates and the VSX
positional cross-match are cached under ``--cache-dir`` and may be reused for
fully reproducible reruns.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from tess_megastructures.annotate.catalog_review_enrichment import (
    build_catalog_review_enrichment,
)
from tess_megastructures.annotate.review_routing import add_catalog_review_routes

MAST_URL = "https://mast.stsci.edu/api/v0/invoke"
XMATCH_URL = "https://cdsxmatch.u-strasbg.fr/xmatch/api/v1/sync"
VSX_CATALOG = "vizier:B/vsx/vsx"
logger = logging.getLogger("build_catalog_review_enrichment")


def _read_table(path: Path) -> pd.DataFrame:
    return (
        pd.read_parquet(path) if path.suffix.lower() in {".parquet", ".pq"} else pd.read_csv(path)
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fetch_tic_coordinates(tic_ids: list[int]) -> pd.DataFrame:
    rows: list[dict] = []
    for start in range(0, len(tic_ids), 150):
        group = tic_ids[start : start + 150]
        request_object = {
            "service": "Mast.Catalogs.Filtered.Tic.Rows",
            "params": {
                "columns": "ID,ra,dec",
                "filters": [{"paramName": "ID", "values": [str(value) for value in group]}],
            },
            "format": "json",
            "pagesize": len(group) + 10,
        }
        body = urllib.parse.urlencode(
            {"request": json.dumps(request_object, separators=(",", ":"))}
        ).encode()
        with urllib.request.urlopen(
            urllib.request.Request(MAST_URL, data=body), timeout=120
        ) as response:
            payload = json.load(response)
        if payload.get("status") != "COMPLETE":
            raise RuntimeError(f"MAST query failed: {payload.get('msg', payload)}")
        rows.extend(payload.get("data", []))
    return pd.DataFrame(rows).rename(columns={"ID": "tic_id"})


def _multipart_body(coordinates: pd.DataFrame, radius_arcsec: float) -> tuple[bytes, str]:
    boundary = "----tess-megastructures-vsx-xmatch"
    csv_bytes = coordinates[["tic_id", "ra", "dec"]].to_csv(index=False).encode()
    fields = {
        "request": "xmatch",
        "distMaxArcsec": str(radius_arcsec),
        "selection": "all",
        "RESPONSEFORMAT": "csv",
        "cat2": VSX_CATALOG,
        "colRA1": "ra",
        "colDec1": "dec",
    }
    out = io.BytesIO()
    for name, value in fields.items():
        out.write(f"--{boundary}\r\n".encode())
        out.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        out.write(str(value).encode())
        out.write(b"\r\n")
    out.write(f"--{boundary}\r\n".encode())
    out.write(b'Content-Disposition: form-data; name="cat1"; filename="tic_coordinates.csv"\r\n')
    out.write(b"Content-Type: text/csv\r\n\r\n")
    out.write(csv_bytes)
    out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), boundary


def _fetch_vsx(coordinates: pd.DataFrame, radius_arcsec: float) -> bytes:
    body, boundary = _multipart_body(coordinates, radius_arcsec)
    request = urllib.request.Request(
        XMATCH_URL,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tces", type=Path, required=True)
    parser.add_argument("--ctoi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--reuse-cache", action="store_true")
    parser.add_argument("--period-column")
    parser.add_argument("--period-tolerance", type=float, default=0.01)
    parser.add_argument("--vsx-radius-arcsec", type=float, default=5.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    coordinates_path = args.cache_dir / "mast_tic_coordinates.csv"
    vsx_path = args.cache_dir / "cds_vsx_xmatch.csv"
    tces = _read_table(args.tces)
    ctoi = _read_table(args.ctoi)

    if args.reuse_cache and coordinates_path.exists():
        coordinates = pd.read_csv(coordinates_path)
    else:
        coordinates = _fetch_tic_coordinates(sorted(tces["tic_id"].dropna().astype(int).unique()))
        coordinates.to_csv(coordinates_path, index=False)
    if args.reuse_cache and vsx_path.exists():
        vsx = pd.read_csv(vsx_path)
    else:
        vsx_path.write_bytes(_fetch_vsx(coordinates, args.vsx_radius_arcsec))
        vsx = pd.read_csv(vsx_path)

    enriched = build_catalog_review_enrichment(
        tces,
        ctoi,
        vsx,
        period_column=args.period_column,
        period_tolerance=args.period_tolerance,
    )
    routed = add_catalog_review_routes(enriched)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix.lower() in {".parquet", ".pq"}:
        routed.to_parquet(args.output, index=False)
    else:
        routed.to_csv(args.output, index=False)

    metrics = {
        "rows": len(routed),
        "unique_tics": int(routed["tic_id"].nunique()),
        "period_tolerance": args.period_tolerance,
        "vsx_radius_arcsec": args.vsx_radius_arcsec,
        "ctoi_host_matches": int(routed["ctoi_host_match"].sum()),
        "ctoi_signal_matches": int(routed["ctoi_signal_match"].sum()),
        "vsx_position_matches": int(routed["vsx_position_match"].sum()),
        "vsx_signal_matches": int(routed["vsx_signal_match"].sum()),
        "automatic_veto_rows": int(routed["catalog_automatic_veto"].sum()),
        "route_counts": routed["catalog_review_route"].value_counts().sort_index().to_dict(),
        "inputs": {
            "tces": str(args.tces),
            "tces_sha256": _sha256(args.tces),
            "ctoi": str(args.ctoi),
            "ctoi_sha256": _sha256(args.ctoi),
            "coordinates_sha256": _sha256(coordinates_path),
            "vsx_sha256": _sha256(vsx_path),
        },
    }
    metrics_path = args.output.with_suffix(args.output.suffix + ".metrics.json")
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    logger.info("wrote %s and %s", args.output, metrics_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
