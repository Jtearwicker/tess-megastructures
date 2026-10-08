"""Build a pinned CTOI/VSX enrichment table for MegaMiner TCEs.

The CTOI snapshot is a required local input. TIC coordinates and the VSX
positional cross-match are cached under ``--cache-dir`` and may be reused for
fully reproducible reruns.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from tess_megastructures.annotate.catalog_review_enrichment import (
    build_catalog_review_enrichment,
)
from tess_megastructures.annotate.review_routing import (
    add_catalog_review_routes,
    attach_catalog_review_to_queue,
)

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


def _coordinates_from_tces(tces: pd.DataFrame) -> pd.DataFrame | None:
    """Use coordinates already carried by the TCE table when available."""
    for ra_column, dec_column in (
        ("ra_deg", "dec_deg"),
        ("tic_ra_deg", "tic_dec_deg"),
        ("doyle_ra_deg", "doyle_dec_deg"),
    ):
        if ra_column in tces and dec_column in tces:
            coordinates = tces[["tic_id", ra_column, dec_column]].rename(
                columns={ra_column: "ra", dec_column: "dec"}
            )
            coordinates = coordinates.dropna().drop_duplicates("tic_id")
            if not coordinates.empty:
                return coordinates
    return None


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


def _fetch_vsx_frame_resilient(
    coordinates: pd.DataFrame, radius_arcsec: float, minimum_batch_size: int = 625
) -> pd.DataFrame:
    """Fetch one batch, recursively splitting uploads that time out."""
    try:
        return pd.read_csv(io.BytesIO(_fetch_vsx(coordinates, radius_arcsec)))
    except Exception:  # noqa: BLE001
        if len(coordinates) <= minimum_batch_size:
            raise
        midpoint = len(coordinates) // 2
        logger.warning("VSX upload failed; splitting %d coordinates", len(coordinates))
        left = _fetch_vsx_frame_resilient(
            coordinates.iloc[:midpoint], radius_arcsec, minimum_batch_size
        )
        right = _fetch_vsx_frame_resilient(
            coordinates.iloc[midpoint:], radius_arcsec, minimum_batch_size
        )
        return pd.concat([left, right], ignore_index=True)


def _fetch_vsx_batched(
    coordinates: pd.DataFrame,
    cache_dir: Path,
    snapshot_date: str,
    radius_arcsec: float,
    batch_size: int,
    reuse_cache: bool,
) -> pd.DataFrame:
    """Run a resumable CDS X-Match in bounded uploads."""
    parts: list[pd.DataFrame] = []
    n_batches = (len(coordinates) + batch_size - 1) // batch_size
    for batch_index, start in enumerate(range(0, len(coordinates), batch_size), start=1):
        part_path = cache_dir / f"vsx_xmatch_{snapshot_date}.part{batch_index:04d}.csv"
        if not (reuse_cache and part_path.exists()):
            batch = coordinates.iloc[start : start + batch_size]
            logger.info("VSX batch %d/%d (%d coordinates)", batch_index, n_batches, len(batch))
            part = _fetch_vsx_frame_resilient(batch, radius_arcsec)
            part.to_csv(part_path, index=False)
            time.sleep(0.2)
        parts.append(pd.read_csv(part_path))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tces", type=Path, required=True)
    parser.add_argument("--ctoi", type=Path, required=True)
    parser.add_argument("--toi", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--queue-input", type=Path)
    parser.add_argument("--queue-output", type=Path)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--reuse-cache", action="store_true")
    parser.add_argument("--period-column")
    parser.add_argument("--period-tolerance", type=float, default=0.01)
    parser.add_argument("--vsx-radius-arcsec", type=float, default=5.0)
    parser.add_argument("--xmatch-batch-size", type=int, default=10000)
    parser.add_argument(
        "--snapshot-date",
        default=dt.date.today().isoformat(),
        help="Date embedded in cached catalog filenames (default: today).",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    coordinates_path = args.cache_dir / f"tic_coordinates_{args.snapshot_date}.csv"
    vsx_path = args.cache_dir / f"vsx_xmatch_{args.snapshot_date}.csv"
    tces = _read_table(args.tces)
    ctoi = _read_table(args.ctoi)
    toi = _read_table(args.toi) if args.toi is not None else None

    if args.reuse_cache and coordinates_path.exists():
        coordinates = pd.read_csv(coordinates_path)
    else:
        coordinates = _coordinates_from_tces(tces)
        if coordinates is None:
            coordinates = _fetch_tic_coordinates(
                sorted(tces["tic_id"].dropna().astype(int).unique())
            )
        coordinates.to_csv(coordinates_path, index=False)
    if args.reuse_cache and vsx_path.exists():
        vsx = pd.read_csv(vsx_path)
    else:
        vsx = _fetch_vsx_batched(
            coordinates,
            args.cache_dir,
            args.snapshot_date,
            args.vsx_radius_arcsec,
            args.xmatch_batch_size,
            args.reuse_cache,
        )
        vsx.to_csv(vsx_path, index=False)

    enriched = build_catalog_review_enrichment(
        tces,
        ctoi,
        vsx,
        toi=toi,
        period_column=args.period_column,
        period_tolerance=args.period_tolerance,
    )
    routed = add_catalog_review_routes(enriched)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix.lower() in {".parquet", ".pq"}:
        routed.to_parquet(args.output, index=False)
    else:
        routed.to_csv(args.output, index=False)

    if (args.queue_input is None) != (args.queue_output is None):
        parser.error("--queue-input and --queue-output must be supplied together")
    if args.queue_input is not None and args.queue_output is not None:
        queue = attach_catalog_review_to_queue(_read_table(args.queue_input), routed)
        args.queue_output.parent.mkdir(parents=True, exist_ok=True)
        if args.queue_output.suffix.lower() in {".parquet", ".pq"}:
            queue.to_parquet(args.queue_output, index=False)
        else:
            queue.to_csv(args.queue_output, index=False)

    metrics = {
        "rows": len(routed),
        "unique_tics": int(routed["tic_id"].nunique()),
        "period_tolerance": args.period_tolerance,
        "vsx_radius_arcsec": args.vsx_radius_arcsec,
        "ctoi_host_matches": int(routed["ctoi_host_match"].sum()),
        "ctoi_signal_matches": int(routed["ctoi_signal_match"].sum()),
        "toi_host_matches": int(routed["toi_host_match"].sum()),
        "toi_signal_matches": int(routed["toi_signal_match"].sum()),
        "vsx_position_matches": int(routed["vsx_position_match"].sum()),
        "vsx_signal_matches": int(routed["vsx_signal_match"].sum()),
        "automatic_veto_rows": int(routed["catalog_automatic_veto"].sum()),
        "route_counts": routed["catalog_review_route"].value_counts().sort_index().to_dict(),
        "queue_rows": len(queue) if args.queue_input is not None else None,
        "inputs": {
            "tces": str(args.tces),
            "tces_sha256": _sha256(args.tces),
            "ctoi": str(args.ctoi),
            "ctoi_sha256": _sha256(args.ctoi),
            "toi": str(args.toi) if args.toi is not None else None,
            "toi_sha256": _sha256(args.toi) if args.toi is not None else None,
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
