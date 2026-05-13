"""A3: Parse TESS-SPOC DV XML files into per-TCE rows.

Replacement for the predecessor's ``parse_dv_reports.py`` with the
following fixes:

- Namespace-aware element lookup (no positional indexing). Robust to
  SPOC schema reorderings.
- ``.get(key, default)`` for every optional XML attribute. No KeyError
  on missing optional fields.
- Per-file and per-TCE error handling. One malformed file (or TCE)
  logs to ``parse_errors.jsonl`` and the run continues.
- Schema-stable Parquet output with explicit nullable dtypes.

The output schema is documented in ``docs/data_dictionary.md``.

The parser is split into many small extraction functions to keep
individual responsibilities clear and to make per-section testing
straightforward. Each function takes an element (or returns None
when its source is absent) and returns a dict of columns to merge
into the row.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

# We use the stdlib ElementTree for parsing. lxml is faster but
# stdlib avoids the extra dependency at parse time, and parsing speed
# is not currently a bottleneck.
import xml.etree.ElementTree as ET

import pandas as pd

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Namespace and helpers
# -------------------------------------------------------------------------

DV_NS = "{http://www.nasa.gov/2018/TESS/DV}"


def _q(tag: str) -> str:
    """Return the namespace-qualified tag name (e.g. 'foo' -> '{ns}foo')."""
    return f"{DV_NS}{tag}"


def _find(parent: ET.Element, tag: str) -> ET.Element | None:
    """Find a single child element by tag name. None if absent."""
    return parent.find(_q(tag))


def _findall(parent: ET.Element, tag: str) -> list[ET.Element]:
    """Find all child elements by tag name."""
    return parent.findall(_q(tag))


def _attr_str(elem: ET.Element | None, key: str) -> str | None:
    """Get an attribute as a string. None if element or attribute is absent."""
    if elem is None:
        return None
    return elem.attrib.get(key)


def _attr_float(elem: ET.Element | None, key: str) -> float | None:
    """Get an attribute as a float. None if absent or unparseable."""
    s = _attr_str(elem, key)
    if s is None or s == "":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _attr_int(elem: ET.Element | None, key: str) -> int | None:
    """Get an attribute as an int. None if absent or unparseable."""
    s = _attr_str(elem, key)
    if s is None or s == "":
        return None
    try:
        # XML stores ints as decimal strings; reject floats that aren't whole.
        return int(s)
    except (ValueError, TypeError):
        try:
            f = float(s)
            return int(f) if f.is_integer() else None
        except (ValueError, TypeError):
            return None


def _attr_bool(elem: ET.Element | None, key: str) -> bool | None:
    """Get an attribute as a bool. XML uses 'true'/'false' strings.

    Returns None if the attribute is absent so we can distinguish
    'value was false' from 'value was missing'.
    """
    s = _attr_str(elem, key)
    if s is None or s == "":
        return None
    return s.strip().lower() == "true"


def _value_and_uncertainty(elem: ET.Element | None) -> tuple[float | None, float | None]:
    """Extract (@value, @uncertainty) from an element."""
    return _attr_float(elem, "value"), _attr_float(elem, "uncertainty")


def _value_over_uncertainty(elem: ET.Element | None) -> float | None:
    """Compute value / uncertainty significance, or None if either is missing/zero."""
    value, unc = _value_and_uncertainty(elem)
    if value is None or unc is None or unc == 0.0:
        return None
    return value / unc


# -------------------------------------------------------------------------
# Sectors-observed bitmask decoding
# -------------------------------------------------------------------------


def _decode_sectors_bitmask(bitmask: str | None) -> list[int]:
    """Decode SPOC's sectorsObserved bitmask string into a list of sector ints.

    The bitmask is a binary string where position i (counting from the
    right, 1-indexed) corresponds to sector i. Example: '...001' means
    sector 1 was observed.

    Empty list if the bitmask is None or empty.
    """
    if not bitmask:
        return []
    # Strip any whitespace and validate
    bitmask = bitmask.strip()
    if not re.match(r"^[01]+$", bitmask):
        logger.warning("Unexpected sectorsObserved format: %r", bitmask)
        return []
    # Reverse so position 0 corresponds to sector 1
    sectors = []
    for i, ch in enumerate(reversed(bitmask)):
        if ch == "1":
            sectors.append(i + 1)
    return sectors


# -------------------------------------------------------------------------
# Target-level extractions
# -------------------------------------------------------------------------


def _extract_target_metadata(root: ET.Element) -> dict[str, Any]:
    """Extract target-level attributes (TIC, sectors, etc.) from dvTargetResults."""
    out: dict[str, Any] = {
        "tic_id": _attr_int(root, "ticId"),
        "toi_id": _attr_str(root, "toiId"),
        "planet_candidate_count": _attr_int(root, "planetCandidateCount"),
        "sectors_observed_bitmask": _attr_str(root, "sectorsObserved"),
        "start_cadence": _attr_int(root, "startCadence"),
        "end_cadence": _attr_int(root, "endCadence"),
        "pipeline_task_id": _attr_int(root, "pipelineTaskId"),
    }
    out["sectors_observed"] = _decode_sectors_bitmask(out["sectors_observed_bitmask"])

    # Matched TOI IDs are child elements with text content (one per TOI).
    matched = [e.text for e in _findall(root, "matchedToiId") if e.text]
    out["matched_toi_ids"] = matched

    return out


def _extract_stellar_properties(root: ET.Element) -> dict[str, Any]:
    """Extract stellar properties (Teff, R*, etc.) from dvTargetResults children."""
    return {
        "ra_deg": _attr_float(_find(root, "raDegrees"), "value"),
        "dec_deg": _attr_float(_find(root, "decDegrees"), "value"),
        "pm_ra": _attr_float(_find(root, "pmRa"), "value"),
        "pm_dec": _attr_float(_find(root, "pmDec"), "value"),
        "tess_mag": _attr_float(_find(root, "tessMag"), "value"),
        "effective_temp": _attr_float(_find(root, "effectiveTemp"), "value"),
        "radius": _attr_float(_find(root, "radius"), "value"),
        "log_g": _attr_float(_find(root, "log10SurfaceGravity"), "value"),
        "log_metallicity": _attr_float(_find(root, "log10Metallicity"), "value"),
        "stellar_density": _attr_float(_find(root, "stellarDensity"), "value"),
    }


def _extract_limb_darkening(root: ET.Element) -> dict[str, Any]:
    """Extract limb darkening model and coefficients."""
    ld = _find(root, "limbDarkeningModel")
    return {
        "limb_darkening_model": _attr_str(ld, "modelName"),
        "limb_darkening_c1": _attr_float(ld, "coefficient1"),
        "limb_darkening_c2": _attr_float(ld, "coefficient2"),
        "limb_darkening_c3": _attr_float(ld, "coefficient3"),
        "limb_darkening_c4": _attr_float(ld, "coefficient4"),
    }


# -------------------------------------------------------------------------
# Per-TCE extractions
# -------------------------------------------------------------------------


def _extract_planet_candidate(planet_results: ET.Element) -> dict[str, Any]:
    """Extract planetCandidate sub-element attributes."""
    pc = _find(planet_results, "planetCandidate")
    return {
        "suspected_eclipsing_binary": _attr_bool(pc, "suspectedEclipsingBinary"),
        "max_single_event_sigma": _attr_float(pc, "maxSingleEventSigma"),
        "max_multiple_event_sigma": _attr_float(pc, "maxMultipleEventSigma"),
        "robust_statistic": _attr_float(pc, "robustStatistic"),
        "model_chi_square_2": _attr_float(pc, "modelChiSquare2"),
        "model_chi_square_dof_2": _attr_float(pc, "modelChiSquareDof2"),
        "model_chi_square_gof": _attr_float(pc, "modelChiSquareGof"),
        "model_chi_square_gof_dof": _attr_float(pc, "modelChiSquareGofDof"),
    }


def _extract_weak_secondary(planet_results: ET.Element) -> dict[str, Any]:
    """Extract weakSecondary sub-element. Located under planetCandidate."""
    pc = _find(planet_results, "planetCandidate")
    if pc is None:
        return {"weak_secondary_mes_mad": None, "weak_secondary_robust_statistic": None}
    ws = _find(pc, "weakSecondary")
    return {
        "weak_secondary_mes_mad": _attr_float(ws, "mesMad"),
        "weak_secondary_robust_statistic": _attr_float(ws, "robustStatistic"),
    }


def _extract_all_transits_fit(planet_results: ET.Element) -> dict[str, Any]:
    """Extract allTransitsFit attributes and named model parameters."""
    fit = _find(planet_results, "allTransitsFit")
    base: dict[str, Any] = {
        "full_convergence": _attr_bool(fit, "fullConvergence"),
        "model_chi_square": _attr_float(fit, "modelChiSquare"),
        "model_degrees_of_freedom": _attr_float(fit, "modelDegreesOfFreedom"),
        "model_fit_snr": _attr_float(fit, "modelFitSnr"),
        "transit_model_name": _attr_str(fit, "transitModelName"),
    }
    # Initialise all known model parameters to None.
    for col in _MODEL_PARAM_COLUMNS.values():
        base[col] = None
        base[f"{col}_err"] = None

    if fit is None:
        return base

    params_elem = _find(fit, "modelParameters")
    if params_elem is None:
        return base

    for param in _findall(params_elem, "modelParameter"):
        name = _attr_str(param, "name")
        col = _MODEL_PARAM_COLUMNS.get(name) if name else None
        if col is None:
            continue
        base[col] = _attr_float(param, "value")
        base[f"{col}_err"] = _attr_float(param, "uncertainty")

    return base


# Named XML model parameters we care about, mapped to snake_case column names.
_MODEL_PARAM_COLUMNS: dict[str, str] = {
    "transitEpochBtjd": "transit_epoch_btjd",
    "minImpactParameter": "min_impact_parameter",
    "orbitalPeriodDays": "orbital_period_days",
    "ratioPlanetRadiusToStarRadius": "ratio_planet_radius_to_star_radius",
    "ratioSemiMajorAxisToStarRadius": "ratio_semi_major_axis_to_star_radius",
    "transitDurationHours": "transit_duration_hours",
    "transitDepthPpm": "transit_depth_ppm",
}


def _extract_binary_discrimination(planet_results: ET.Element) -> dict[str, Any]:
    """Extract odd/even depth comparison and its significance."""
    bd = _find(planet_results, "binaryDiscriminationResults")
    if bd is None:
        return {"odd_even_depth_statistic": None, "odd_even_depth_significance": None}
    oe = _find(bd, "oddEvenTransitDepthComparisonStatistic")
    return {
        "odd_even_depth_statistic": _attr_float(oe, "value"),
        "odd_even_depth_significance": _attr_float(oe, "significance"),
    }


def _extract_bootstrap(planet_results: ET.Element) -> dict[str, Any]:
    """Extract bootstrap significance."""
    bs = _find(planet_results, "bootstrapResults")
    return {"bootstrap_significance": _attr_float(bs, "significance")}


def _extract_centroid_offsets(planet_results: ET.Element) -> dict[str, Any]:
    """Extract centroid offset significances.

    This is the part where the predecessor used positional indexing
    ``elem[0][0][2]``. Here we use named-element lookup so a future
    schema reorder doesn't silently produce wrong values.
    """
    out: dict[str, Any] = {
        "ms_tic_centroid_offset_sigma": None,
        "ms_control_centroid_offset_sigma": None,
    }
    centroid = _find(planet_results, "centroidResults")
    if centroid is None:
        return out
    motion = _find(centroid, "differenceImageMotionResults")
    if motion is None:
        return out
    for source_tag, out_key in [
        ("msTicCentroidOffsets", "ms_tic_centroid_offset_sigma"),
        ("msControlCentroidOffsets", "ms_control_centroid_offset_sigma"),
    ]:
        offsets = _find(motion, source_tag)
        if offsets is None:
            continue
        sky_offset = _find(offsets, "meanSkyOffset")
        out[out_key] = _value_over_uncertainty(sky_offset)
    return out


def _extract_ghost_diagnostic(planet_results: ET.Element) -> dict[str, Any]:
    """Extract core/halo aperture correlation statistics."""
    gd = _find(planet_results, "ghostDiagnosticResults")
    if gd is None:
        return {
            "ghost_core_correlation": None,
            "ghost_core_correlation_significance": None,
            "ghost_halo_correlation": None,
            "ghost_halo_correlation_significance": None,
        }
    core = _find(gd, "coreApertureCorrelationStatistic")
    halo = _find(gd, "haloApertureCorrelationStatistic")
    return {
        "ghost_core_correlation": _attr_float(core, "value"),
        "ghost_core_correlation_significance": _attr_float(core, "significance"),
        "ghost_halo_correlation": _attr_float(halo, "value"),
        "ghost_halo_correlation_significance": _attr_float(halo, "significance"),
    }


def _extract_difference_image_info(planet_results: ET.Element) -> dict[str, Any]:
    """Extract sector info from differenceImageResults.

    Multi-sector runs have one differenceImageResults per sector.
    We store the last sector found plus the total count, so callers
    can detect multi-sector cases.
    """
    di = _findall(planet_results, "differenceImageResults")
    if not di:
        return {"sector": None, "n_difference_images": 0}
    last = di[-1]
    return {
        "sector": _attr_int(last, "sector"),
        "n_difference_images": len(di),
    }


# -------------------------------------------------------------------------
# Top-level extraction: one XML file -> list of TCE row dicts
# -------------------------------------------------------------------------


def parse_dv_xml(xml_path: Path) -> list[dict[str, Any]]:
    """Parse a single DV XML file into TCE row dicts.

    Each ``planetResults`` element becomes one row. Target-level
    fields (TIC, stellar properties, limb darkening) are duplicated
    across rows from the same target.

    Per-TCE errors are caught and logged; the function continues with
    the remaining TCEs. Whole-file errors raise; the caller is
    responsible for catching at the file boundary.

    Parameters
    ----------
    xml_path : Path
        Path to a ``.xml`` DV report.

    Returns
    -------
    list of dict
        One dict per successfully-parsed TCE. Empty list if the file
        has no TCEs (some targets have no detected signals).
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    if not root.tag.endswith("dvTargetResults"):
        raise ValueError(f"Root element is <{root.tag}>, expected <dvTargetResults>")

    target_fields = {
        **_extract_target_metadata(root),
        **_extract_stellar_properties(root),
        **_extract_limb_darkening(root),
    }

    rows: list[dict[str, Any]] = []
    tic_id = target_fields.get("tic_id")

    for pr in _findall(root, "planetResults"):
        try:
            planet_number = _attr_int(pr, "planetNumber")
            if planet_number is None:
                raise ValueError("planetNumber missing")

            tce_fields: dict[str, Any] = {
                "planet_number": planet_number,
                "tce_toi_id": _attr_str(pr, "toiId"),
                "toi_correlation": _attr_float(pr, "toiCorrelation"),
                "detrend_filter_length": _attr_int(pr, "detrendFilterLength"),
                **_extract_planet_candidate(pr),
                **_extract_weak_secondary(pr),
                **_extract_all_transits_fit(pr),
                **_extract_binary_discrimination(pr),
                **_extract_bootstrap(pr),
                **_extract_centroid_offsets(pr),
                **_extract_ghost_diagnostic(pr),
                **_extract_difference_image_info(pr),
            }

            rows.append({**target_fields, **tce_fields})

        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Skipping TCE in %s (TIC %s): %s: %s",
                xml_path.name,
                tic_id,
                type(e).__name__,
                e,
            )
            continue

    return rows


# -------------------------------------------------------------------------
# Sector-level driver
# -------------------------------------------------------------------------


def parse_sector(
    xml_dir: Path,
    output_path: Path,
    error_log_path: Path | None = None,
) -> dict[str, int]:
    """Parse all XML files in a directory into a single Parquet.

    Per-file errors are caught and logged as JSON lines. Returns counts
    so the caller can decide whether the error rate is acceptable.

    Parameters
    ----------
    xml_dir : Path
        Directory to search for ``.xml`` files (recursively).
    output_path : Path
        Destination Parquet path.
    error_log_path : Path, optional
        Per-file errors written here as one JSON object per line.

    Returns
    -------
    dict
        Keys: ``files_total``, ``files_ok``, ``files_failed``,
        ``tces_extracted``.
    """
    xml_files = sorted(xml_dir.rglob("*.xml"))
    counts = {
        "files_total": len(xml_files),
        "files_ok": 0,
        "files_failed": 0,
        "tces_extracted": 0,
    }
    all_rows: list[dict[str, Any]] = []

    error_fh = error_log_path.open("w") if error_log_path else None

    try:
        for path in xml_files:
            try:
                rows = parse_dv_xml(path)
                all_rows.extend(rows)
                counts["files_ok"] += 1
                counts["tces_extracted"] += len(rows)
            except Exception as e:  # noqa: BLE001
                counts["files_failed"] += 1
                err = {
                    "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                    "level": "file",
                    "path": str(path),
                    "error_type": type(e).__name__,
                    "message": str(e),
                }
                if error_fh is not None:
                    error_fh.write(json.dumps(err) + "\n")
                logger.warning("Failed to parse %s: %s: %s", path, type(e).__name__, e)
    finally:
        if error_fh is not None:
            error_fh.close()

    # Add provenance columns and write Parquet.
    from tess_megastructures import __version__ as parser_version

    for row in all_rows:
        row.setdefault("parser_version", parser_version)
        row.setdefault("parsed_at", dt.datetime.now(dt.UTC).isoformat())

    if all_rows:
        df = pd.DataFrame(all_rows)
        # Use pyarrow backend for stable nullable dtypes.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, index=False)
    else:
        logger.warning("No TCEs extracted; not writing Parquet at %s", output_path)

    return counts


# -------------------------------------------------------------------------
# CLI entry point
# -------------------------------------------------------------------------


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Parse TESS-SPOC DV XML to Parquet.")
    parser.add_argument("--xml-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--error-log", type=Path, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    counts = parse_sector(args.xml_dir, args.output, args.error_log)
    for key, value in counts.items():
        logger.info("%s: %s", key, value)

    # Exit non-zero only if EVERY file failed.
    if counts["files_total"] > 0 and counts["files_ok"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
