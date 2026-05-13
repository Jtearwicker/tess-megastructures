"""Download a single DV XML file from MAST for use as a parser test fixture.

This is a one-time script. Run it once, commit the resulting XML to
tests/fixtures/, then this script can be deleted or kept for reference.

Filters TESS-SPOC HLSP products using the 'description' field
('Informational XML') and the 'productFilename' ending in '_dvr.xml',
since TESS-SPOC HLSP products don't populate `productSubGroupDescription`.

Usage:
    uv run python scripts/download_test_fixture.py

The script downloads the DV XML for TIC 307210830 (TOI-700) for the
sector chosen below. TOI-700 is a well-studied multi-planet system, so
the resulting fixture exercises the parser's multi-TCE code path.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# Target sector for the fixture. Choose a single-sector run that falls
# inside the project's scope (sectors 36-80). s0063 is mid-range and
# well after SPOC FFI processing stabilized.
PREFERRED_SECTOR = "s0063"


def main() -> int:
    try:
        from astroquery.mast import Observations
    except ImportError:
        print("ERROR: astroquery not installed. Run: uv sync --extra all")
        return 1

    tic_id = 307210830
    repo_root = Path(__file__).resolve().parent.parent
    fixture_dir = repo_root / "tests" / "fixtures"
    fixture_path = fixture_dir / "example_dv.xml"
    fixture_dir.mkdir(parents=True, exist_ok=True)

    print(f"Searching MAST for TIC {tic_id}...")
    obs = Observations.query_criteria(
        target_name=str(tic_id),
        obs_collection="HLSP",
        provenance_name="TESS-SPOC",
    )
    print(f"Found {len(obs)} TESS-SPOC observation(s).")

    if len(obs) == 0:
        print("No observations found. Cannot continue.")
        return 1

    print("Fetching product list...")
    products = Observations.get_product_list(obs)
    print(f"Got {len(products)} products.")

    # Filter to DVR XML files. TESS-SPOC HLSP uses description='Informational
    # XML' and a filename ending in '_dvr.xml'. The single-sector runs have
    # filenames like '...-s0063-s0063_tess_v1_dvr.xml'; multi-sector runs
    # have filenames like '...-s0056-s0069_tess_v1_dvr.xml'.
    is_xml = [str(f).endswith("_dvr.xml") for f in products["productFilename"]]
    dvr_xml = products[is_xml]
    print(f"\nFound {len(dvr_xml)} DVR XML files:")
    for f in dvr_xml["productFilename"]:
        print(f"  {f}")

    if len(dvr_xml) == 0:
        print("No DVR XML files found. Cannot continue.")
        return 1

    # Pick the file matching our preferred sector.
    preferred_pattern = f"-{PREFERRED_SECTOR}-{PREFERRED_SECTOR}_"
    matches = [i for i, fn in enumerate(dvr_xml["productFilename"]) if preferred_pattern in str(fn)]

    if matches:
        chosen_index = matches[0]
    else:
        # Fall back to whatever single-sector file we can find
        single_sector_matches = [
            i
            for i, fn in enumerate(dvr_xml["productFilename"])
            if str(fn).count("-s") == 2  # exactly two -sXXXX tokens = single sector
        ]
        if single_sector_matches:
            chosen_index = single_sector_matches[0]
            print(
                f"\nPreferred sector {PREFERRED_SECTOR} not available; "
                f"falling back to: {dvr_xml['productFilename'][chosen_index]}"
            )
        else:
            chosen_index = 0
            print(
                f"\nNo single-sector files available; using multi-sector: "
                f"{dvr_xml['productFilename'][chosen_index]}"
            )

    chosen_filename = dvr_xml["productFilename"][chosen_index]
    print(f"\nSelected: {chosen_filename}")

    chosen_row = dvr_xml[chosen_index : chosen_index + 1]
    manifest = Observations.download_products(chosen_row, download_dir=str(fixture_dir))

    downloaded_path = Path(manifest[0]["Local Path"])
    if not downloaded_path.exists():
        print(f"ERROR: manifest reports {downloaded_path} but file is missing.")
        return 1

    shutil.copy(downloaded_path, fixture_path)
    print(f"\n[OK] Copied to {fixture_path}")
    print(f"     Original filename: {chosen_filename}")
    print(f"     Size: {fixture_path.stat().st_size:,} bytes")

    # Quick sanity check
    with open(fixture_path) as f:
        first_line = f.readline().strip()
    if not first_line.startswith("<?xml"):
        print(f"WARNING: file doesn't look like XML. First line: {first_line!r}")
        return 1
    print("[OK] XML sanity check passed.")

    # Quick count of TCEs
    import xml.etree.ElementTree as ET

    tree = ET.parse(fixture_path)
    root = tree.getroot()
    ns = {"dv": "http://www.nasa.gov/2018/TESS/DV"}
    tces = root.findall("dv:planetResults", ns)
    print(f"[OK] Contains {len(tces)} TCE(s).")

    print("\nNext step: commit the fixture")
    print("  git add tests/fixtures/example_dv.xml")
    print('  git commit -m "Add DV XML test fixture for TIC 307210830"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
