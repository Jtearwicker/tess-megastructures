"""A2: Download TESS-SPOC Data Validation XML files from MAST.

Replaces the predecessor's ``generate_tce_data.py`` bash-driven download with:
- Resumable, parallel downloads (ThreadPoolExecutor)
- Per-file integrity checks (XML is well-formed)
- Per-file failure tolerance (one bad file doesn't crash the run)
- State manifest updates so re-runs skip already-downloaded files

The MAST DV retrieval scripts are downloaded from:
``https://archive.stsci.edu/hlsps/tess-spoc/download_scripts/``
Each script contains many ``curl`` commands, one per data product. We
filter to the DV report XML (``*dvr.xml``) and execute those in parallel
via Python rather than shelling out to bash.

CLI (called by workflow/rules/ingest.smk :: download_sector_xml):
    python -m tess_megastructures.ingest.download \\
        --sector-run s0056 --output-dir <xml_dir>/s0056 --max-concurrent 8

Exit code 0 on success (Snakemake then touches the .download_complete
marker); non-zero if the retrieval script can't be fetched or every file
fails. Per-file failures are tolerated and counted.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RETRIEVAL_SCRIPT_BASE = (
    "https://archive.stsci.edu/hlsps/tess-spoc/download_scripts/"
)

# a curl line in the retrieval script looks like:
#   curl -L -o ./path/to/hlsp_..._dvr.xml "https://mast.../file.xml"
# we pull out (local_relpath, url). Robust to flag ordering and quoting.
_CURL_OUT_RE = re.compile(r"(?:--output|-o)\s+(?P<out>'[^']*'|\"[^\"]*\"|\S+)")
_CURL_URL_RE = re.compile(r"(https?://\S+?)(?:['\"]|\s|$)")


def retrieval_script_url(sector_run: str) -> str:
    """URL of the MAST DV retrieval script for a sector run."""
    return (
        RETRIEVAL_SCRIPT_BASE
        + f"hlsp_tess-spoc_tess_phot_{sector_run}_tess_v1_dl-dv.sh"
    )


def fetch_retrieval_script(sector_run: str, timeout: int = 60) -> str:
    """Download the retrieval-script text for a sector run."""
    url = retrieval_script_url(sector_run)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_curl_lines(script_text: str) -> list[tuple[str, str]]:
    """Extract (local_relpath, url) pairs for DV report XML files.

    Only keeps DV reports (``dvr.xml``) -- the per-TCE XML the parser reads.
    Skips fits, pdf, and non-report xml (dvt/dvs).
    """
    pairs: list[tuple[str, str]] = []
    for line in script_text.splitlines():
        line = line.strip()
        if not line.startswith("curl"):
            continue
        m_out = _CURL_OUT_RE.search(line)
        m_url = _CURL_URL_RE.search(line)
        if not (m_out and m_url):
            continue
        out = m_out.group("out").strip("'\"")
        url = m_url.group(1).strip("'\"")
        if out.endswith("dvr.xml"):
            pairs.append((out, url))
    return pairs


def _xml_ok(path: Path) -> bool:
    """True if the file parses as well-formed XML."""
    try:
        ET.parse(str(path))
        return True
    except (ET.ParseError, OSError):
        return False


def _download_one(
    relpath: str, url: str, output_dir: Path, skip_existing: bool
) -> str:
    """Download a single file. Returns 'ok', 'skipped', or 'failed'."""
    # relpath from the script is like ./target/0000/.../file_dvr.xml
    dest = output_dir / Path(relpath.lstrip("./"))
    if skip_existing and dest.exists() and _xml_ok(dest):
        return "skipped"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        urllib.request.urlretrieve(url, str(tmp))
        if not _xml_ok(tmp):
            tmp.unlink(missing_ok=True)
            return "failed"
        tmp.replace(dest)  # atomic move into place
        return "ok"
    except Exception:
        tmp.unlink(missing_ok=True)
        return "failed"


def download_sector_xml(
    sector_run: str,
    output_dir: Path,
    max_concurrent: int = 8,
    skip_existing: bool = True,
) -> dict[str, int]:
    """Download all DV XML files for a sector run.

    Returns counts of ``downloaded``, ``skipped``, ``failed``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    script = fetch_retrieval_script(sector_run)
    pairs = parse_curl_lines(script)
    if not pairs:
        raise RuntimeError(
            f"no DV report XML entries found in retrieval script for "
            f"{sector_run} (script had {len(script.splitlines())} lines)"
        )

    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    with ThreadPoolExecutor(max_workers=max_concurrent) as ex:
        futs = {
            ex.submit(_download_one, rel, url, output_dir, skip_existing): rel
            for rel, url in pairs
        }
        for fut in as_completed(futs):
            result = fut.result()
            if result == "ok":
                counts["downloaded"] += 1
            elif result == "skipped":
                counts["skipped"] += 1
            else:
                counts["failed"] += 1
    return counts


def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Download TESS-SPOC DV XML for a sector.")
    ap.add_argument("--sector-run", required=True, help="e.g. s0056 or s0056-s0069")
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--max-concurrent", type=int, default=8)
    ap.add_argument("--no-skip-existing", action="store_true",
                    help="re-download even if a valid file already exists")
    ap.add_argument("--manifest-path", type=Path, default=None,
                    help="optional SQLite manifest to record the download in")
    ap.add_argument("--complete-marker", type=Path, default=None,
                    help="path to a marker file to touch on success (for Snakemake)")
    args = ap.parse_args(argv)

    try:
        counts = download_sector_xml(
            args.sector_run,
            args.output_dir,
            max_concurrent=args.max_concurrent,
            skip_existing=not args.no_skip_existing,
        )
    except Exception as e:
        print(f"ERROR: download failed for {args.sector_run}: {e}", file=sys.stderr)
        return 1

    n_ok = counts["downloaded"] + counts["skipped"]
    print(
        f"{args.sector_run}: downloaded={counts['downloaded']} "
        f"skipped={counts['skipped']} failed={counts['failed']}",
        file=sys.stderr,
    )

    # record to manifest if requested
    if args.manifest_path is not None:
        try:
            from tess_megastructures.ingest import manifest as m
            conn = m.init_manifest(args.manifest_path)
            m.record_download(conn, args.sector_run,
                              n_files_downloaded=counts["downloaded"],
                              n_files_failed=counts["failed"])
        except Exception as e:
            print(f"WARN: manifest update failed: {e}", file=sys.stderr)

    # fail the job only if nothing succeeded at all
    if n_ok == 0:
        print("ERROR: no files downloaded successfully", file=sys.stderr)
        return 1

    # Stamp completion ourselves rather than relying on Snakemake's touch(),
    # which was observed not to fire reliably for this rule. The process that
    # did the work is the authority on whether it finished.
    if args.complete_marker is not None:
        args.complete_marker.parent.mkdir(parents=True, exist_ok=True)
        args.complete_marker.touch()

    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
