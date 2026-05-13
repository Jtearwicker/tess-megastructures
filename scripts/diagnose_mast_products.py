"""Diagnostic: list what astroquery returns for TIC 307210830.

Just dumps the product list without trying to filter. Use this to figure
out which column and value to filter on for XML files in TESS-SPOC HLSP.

Run:
    uv run python scripts/diagnose_mast_products.py
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from astroquery.mast import Observations
    except ImportError:
        print("astroquery not installed")
        return 1

    tic_id = 307210830

    print(f"Searching MAST for TIC {tic_id}...")
    obs = Observations.query_criteria(
        target_name=str(tic_id),
        obs_collection="HLSP",
        provenance_name="TESS-SPOC",
    )
    print(f"Found {len(obs)} observations.")

    print("\n--- Observation columns ---")
    print(obs.colnames)

    print("\n--- First 3 observations (selected cols) ---")
    cols_of_interest = [c for c in ["obs_id", "obs_collection", "provenance_name",
                                     "sequence_number", "target_name", "dataproduct_type"]
                        if c in obs.colnames]
    print(obs[cols_of_interest][:3])

    print("\nFetching product list for all observations...")
    products = Observations.get_product_list(obs)
    print(f"Got {len(products)} products.")

    print("\n--- Product columns ---")
    print(products.colnames)

    print("\n--- Sample of productFilename values (first 30) ---")
    if "productFilename" in products.colnames:
        for fn in products["productFilename"][:30]:
            print(f"  {fn}")

    print("\n--- Files containing 'xml' (any case) ---")
    if "productFilename" in products.colnames:
        xml_files = [str(f) for f in products["productFilename"] if "xml" in str(f).lower()]
        print(f"Total XML files: {len(xml_files)}")
        for fn in xml_files[:20]:
            print(f"  {fn}")
        if len(xml_files) > 20:
            print(f"  ... and {len(xml_files) - 20} more")

    print("\n--- Unique values of useful filter columns ---")
    for col in ["productType", "productGroupDescription", "productSubGroupDescription",
                "dataproduct_type", "type", "description"]:
        if col in products.colnames:
            # Handle masked values
            try:
                unique_vals = set()
                for v in products[col]:
                    try:
                        unique_vals.add(str(v))
                    except Exception:
                        unique_vals.add("<unrepresentable>")
                print(f"\n{col}: {sorted(unique_vals)}")
            except Exception as e:
                print(f"\n{col}: error reading - {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
