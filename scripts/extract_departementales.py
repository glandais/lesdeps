#!/usr/bin/env python3
"""
Extract D-roads (Départementales) and M-roads (Métropolitaines) from OSM PBF file.

Uses pyosmium for extraction and dynamically detects département from road location.
M-roads are merged into corresponding D-roads when:
- old_ref tag confirms the relationship, OR
- The M-road is within 3km of the corresponding D-road

Outputs a combined GeoJSON file and index.json for the web viewer.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import osmium
import shapely
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

# Minimum total length (main + variants) to include a road
MIN_TOTAL_LENGTH_KM = 10


class DRoadHandler(osmium.SimpleHandler):
    """Collect D-road and M-road ways with geometries using WKBFactory."""

    def __init__(self, departements: Dict[str, any]):
        super().__init__()
        self.wkb_factory = osmium.geom.WKBFactory()
        self.ways = []
        self.departements = departements
        self.i = 0

    def way(self, w):
        if "highway" not in w.tags:
            return

        ref = w.tags.get("ref", "")
        old_ref = w.tags.get("old_ref", "")

        # Check for D/M road refs
        road_refs = parse_road_refs(ref)
        old_road_refs = parse_road_refs(old_ref)

        if not road_refs and not old_road_refs:
            return

        # Use old_ref if no current refs
        if not road_refs:
            road_refs = old_road_refs
            old_road_refs = []  # Already using old_ref as primary

        # Check for M→D confirmation via old_ref
        old_ref_confirmed = {}
        for r in road_refs:
            if r.startswith("M"):
                # Check if old_ref contains corresponding D road
                d_equivalent = "D" + r[1:]
                if d_equivalent in old_road_refs:
                    old_ref_confirmed[r] = d_equivalent

        try:
            wkb = self.wkb_factory.create_linestring(w)
            geom = shapely.from_wkb(wkb)
            if geom.is_empty:
                return
            # Determine département
            dept_code = find_departement(geom, self.departements)
            if not dept_code:
                return
            self.i = self.i + 1
            if self.i % 5000 == 0:
                print(f"  Processed {self.i} ways...")
            self.ways.append(
                {
                    "road_refs": road_refs,
                    "old_ref_confirmed": old_ref_confirmed,
                    "dept_code": dept_code,
                    "geom": geom,
                }
            )
        except osmium.InvalidLocationError:
            pass  # Incomplete way (nodes outside extract)


def load_departements(geojson_path: Path) -> Dict[str, any]:
    """
    Load département boundaries from GeoJSON file.

    Args:
        geojson_path: Path to departements.geojson file

    Returns:
        Dict mapping département code (e.g., "44") to shapely geometry
    """
    print(f"Loading département boundaries from {geojson_path}...")

    with open(geojson_path) as f:
        data = json.load(f)

    departements = {}
    for feature in data.get("features", []):
        code = feature.get("properties", {}).get("code")
        geometry = shape(feature["geometry"])
        departements[code] = geometry
        nom = feature.get("properties", {}).get("nom", "")
        print(f"  Loaded {code} - {nom}")

    return departements


def find_departement(geometry, departements: Dict[str, any]) -> Optional[str]:
    """
    Find which département a road geometry belongs to.
    Returns the département with the longest intersection.
    """
    if not departements or geometry is None:
        return None

    try:
        best_dept = None
        best_length = 0.0

        for dept_code, dept_geom in departements.items():
            # Quick check: if fully contained, return immediately
            if dept_geom.contains(geometry):
                return dept_code

            # Calculate intersection length
            if dept_geom.intersects(geometry):
                intersection = geometry.intersection(dept_geom)
                if not intersection.is_empty:
                    length = intersection.length
                    if length > best_length:
                        best_length = length
                        best_dept = dept_code

        return best_dept

    except Exception:
        pass

    return None


def parse_road_refs(ref_string: str) -> List[str]:
    """
    Parse ref string and extract D/M road references.

    Handles:
    - Single ref: "D17" -> ["D17"], "M17" -> ["M17"]
    - Multiple refs: "D17;D18" -> ["D17", "D18"]
    - Variants: "D17A", "M17bis" -> ["D17A"], ["M17BIS"]
    """
    if not ref_string:
        return []

    refs = [r.strip() for r in str(ref_string).split(";")]
    road_refs = []

    for r in refs:
        # Remove spaces
        r = r.replace(" ", "")
        # Match D or M roads (D/M followed by digits, optional variant suffix)
        if re.match(r"^[DM]\d+[a-zA-Z]*$", r, re.IGNORECASE):
            road_refs.append(r.upper())

    return road_refs


def parse_road_ref(ref: str, dept_code: str) -> Tuple[str, str, bool, str]:
    """
    Parse road reference into prefixed ref, variant detection, and parent ref.

    Examples (with dept_code="44"):
        D17 -> ('44-D17', '', False, '')
        D17A -> ('44-D17A', 'A', True, '44-D17')
        D17BIS -> ('44-D17BIS', 'BIS', True, '44-D17')
        M17 -> ('44-M17', '', False, '')
        M17A -> ('44-M17A', 'A', True, '44-M17')

    Returns:
        (prefixed_ref, variant, is_variant, parent_ref)
    """
    match = re.match(r"^([DM]\d+)([A-Z]{1,3})?$", ref, re.IGNORECASE)
    if match:
        base = match.group(1).upper()
        variant = (match.group(2) or "").upper()

        prefixed_base = f"{dept_code}-{base}"
        prefixed_ref = f"{dept_code}-{base}{variant}" if variant else prefixed_base

        is_variant = bool(variant)
        parent_ref = prefixed_base if is_variant else ""

        return (prefixed_ref, variant, is_variant, parent_ref)

    # Fallback
    prefixed_ref = f"{dept_code}-{ref.upper()}"
    return (prefixed_ref, "", False, "")


# Transformer from WGS84 (EPSG:4326) to Lambert-93 (EPSG:2154) for accurate length in France
_transformer = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)


def calculate_length_km(geom) -> float:
    """Calculate accurate length in kilometers using Lambert-93 projection."""
    projected = transform(_transformer.transform, geom)
    return projected.length / 1000.0


def min_distance_km(geom1, geom2) -> float:
    """Calculate minimum distance in km between two geometries using Lambert-93."""
    geom1_proj = transform(_transformer.transform, geom1)
    geom2_proj = transform(_transformer.transform, geom2)
    return geom1_proj.distance(geom2_proj) / 1000.0


def extract_roads(
    pbf_file: Path, departements: Dict[str, any]
) -> Dict[str, List[dict]]:
    """
    Extract D/M roads from OSM PBF file using pyosmium.

    Returns:
        Dictionary mapping road refs (with dept prefix) to list of features
    """
    print("Extracting D/M road ways...")
    handler = DRoadHandler(departements)
    handler.apply_file(str(pbf_file), locations=True)
    print(f"  Found {len(handler.ways)} road segments")

    print("Processing ways...")
    roads_by_ref = defaultdict(list)
    # Track old_ref confirmations and geometries for M→D merging
    old_ref_confirmations = {}  # Maps prefixed M-ref → prefixed D-ref
    geometries_by_ref = defaultdict(list)  # For distance calculations

    for i, way in enumerate(handler.ways):
        # Calculate accurate length in km using Lambert-93 projection
        length_km = calculate_length_km(way["geom"])

        # Create features for each road ref
        for road_ref in way["road_refs"]:
            prefixed_ref, variant, is_variant, parent_ref = parse_road_ref(
                road_ref, way["dept_code"]
            )

            feature = {
                "type": "Feature",
                "properties": {
                    "ref": prefixed_ref,
                    "dept": way["dept_code"],
                    "variant": variant,
                    "is_variant": is_variant,
                    "parent_ref": parent_ref,
                    "length_km": round(length_km, 3),
                },
                "geometry": way["geom"].__geo_interface__,
            }

            roads_by_ref[prefixed_ref].append(feature)
            geometries_by_ref[prefixed_ref].append(way["geom"])

            # Track old_ref confirmations for M-roads
            if road_ref in way["old_ref_confirmed"]:
                d_equivalent = way["old_ref_confirmed"][road_ref]
                d_prefixed = f"{way['dept_code']}-{d_equivalent}"
                old_ref_confirmations[prefixed_ref] = d_prefixed

    print(f"\nExtraction summary:")
    print(f"  Found {len(roads_by_ref)} unique road references")

    # Merge M-roads into D-roads where appropriate
    roads_by_ref = merge_m_into_d(
        roads_by_ref, geometries_by_ref, old_ref_confirmations
    )

    return roads_by_ref


def merge_m_into_d(
    roads_by_ref: Dict[str, List[dict]],
    geometries_by_ref: Dict[str, List],
    old_ref_confirmations: Dict[str, str],
) -> Dict[str, List[dict]]:
    """
    Merge M-roads into corresponding D-roads based on old_ref or proximity.

    Strategy:
    1. If old_ref confirms M→D relationship: merge
    2. If M-road is within 3km of corresponding D-road: merge
    3. Otherwise: keep M-road separate
    """
    from shapely.ops import unary_union

    MERGE_DISTANCE_KM = 3.0

    # Find all M-roads
    m_roads = [ref for ref in roads_by_ref.keys() if "-M" in ref]

    if not m_roads:
        return roads_by_ref

    print(f"\nProcessing {len(m_roads)} M-roads for potential merge...")
    merged_count = 0
    kept_count = 0

    for m_ref in m_roads:
        # Extract département and number: "44-M17" → "44", "17"
        match = re.match(r"^(\d+)-M(\d+[A-Z]*)$", m_ref)
        if not match:
            kept_count += 1
            continue

        dept_code = match.group(1)
        road_num = match.group(2)
        d_ref = f"{dept_code}-D{road_num}"

        should_merge = False
        merge_reason = ""

        # Case 1: old_ref confirms relationship
        if m_ref in old_ref_confirmations:
            confirmed_d = old_ref_confirmations[m_ref]
            if confirmed_d == d_ref:
                should_merge = True
                merge_reason = "old_ref confirmed"

        # Case 2: Check spatial proximity (only if D-road exists)
        if not should_merge and d_ref in roads_by_ref:
            # Combine all geometries for each road
            m_geoms = geometries_by_ref.get(m_ref, [])
            d_geoms = geometries_by_ref.get(d_ref, [])

            if m_geoms and d_geoms:
                m_combined = unary_union(m_geoms)
                d_combined = unary_union(d_geoms)
                distance = min_distance_km(m_combined, d_combined)

                if distance < MERGE_DISTANCE_KM:
                    should_merge = True
                    merge_reason = f"proximity ({distance:.1f}km)"

        if should_merge:
            # Merge M-road features into D-road
            m_features = roads_by_ref.pop(m_ref)

            # Update feature properties to use D reference
            for feature in m_features:
                old_ref_val = feature["properties"]["ref"]
                feature["properties"]["ref"] = d_ref
                feature["properties"]["original_ref"] = old_ref_val

                # Update variant parent_ref if applicable
                if feature["properties"]["is_variant"]:
                    # M17A parent was 44-M17, now should be 44-D17
                    old_parent = feature["properties"]["parent_ref"]
                    if old_parent:
                        feature["properties"]["parent_ref"] = old_parent.replace(
                            "-M", "-D"
                        )

            # Ensure D-road exists in roads_by_ref
            if d_ref not in roads_by_ref:
                roads_by_ref[d_ref] = []

            roads_by_ref[d_ref].extend(m_features)
            merged_count += 1
            print(f"  Merged {m_ref} → {d_ref} ({merge_reason})")
        else:
            kept_count += 1

    print(f"  Merged: {merged_count}, Kept separate: {kept_count}")

    return roads_by_ref


def calculate_road_metadata(road_ref: str, features: List[dict]) -> dict:
    """Calculate metadata for a road reference."""
    total_length_km = sum(f["properties"]["length_km"] for f in features)

    first_feature = features[0]["properties"]
    is_variant = first_feature.get("is_variant", False)
    parent_ref = first_feature.get("parent_ref", "")

    # Calculate bounding box from all geometries
    min_lon, min_lat = float("inf"), float("inf")
    max_lon, max_lat = float("-inf"), float("-inf")

    for feature in features:
        geom = feature["geometry"]
        coords = geom["coordinates"]
        # Handle LineString
        if geom["type"] == "LineString":
            for lon, lat in coords:
                min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
        # Handle MultiLineString
        elif geom["type"] == "MultiLineString":
            for line in coords:
                for lon, lat in line:
                    min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                    min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)

    return {
        "ref": road_ref,
        "length_km": round(total_length_km, 3),
        "segment_count": len(features),
        "is_variant": is_variant,
        "variant_of": parent_ref if is_variant else None,
        "bounds": [
            round(min_lon, 6),
            round(min_lat, 6),
            round(max_lon, 6),
            round(max_lat, 6),
        ],
    }


def write_all_roads_geojson(
    roads_by_ref: Dict[str, List[dict]], output_dir: Path
) -> List[dict]:
    """Write single roads.geojson with all features and return metadata list."""
    filepath = output_dir / "roads.geojson"

    # First pass: calculate metadata for all roads
    metadata_list = []
    for road_ref in sorted(roads_by_ref.keys()):
        features = roads_by_ref[road_ref]
        metadata = calculate_road_metadata(road_ref, features)
        metadata_list.append(metadata)

    # Build lookup: main road ref -> total length (main + variants)
    main_road_total_length = {}
    for meta in metadata_list:
        if not meta["is_variant"]:
            main_road_total_length[meta["ref"]] = meta["length_km"]

    # Add variant lengths to their parent
    for meta in metadata_list:
        if meta["is_variant"] and meta["variant_of"]:
            parent = meta["variant_of"]
            if parent in main_road_total_length:
                main_road_total_length[parent] += meta["length_km"]

    # Build lookup: any ref -> total length of its family
    ref_to_total_length = {}
    for meta in metadata_list:
        if meta["is_variant"] and meta["variant_of"]:
            ref_to_total_length[meta["ref"]] = main_road_total_length.get(
                meta["variant_of"], meta["length_km"]
            )
        else:
            ref_to_total_length[meta["ref"]] = main_road_total_length.get(
                meta["ref"], meta["length_km"]
            )

    # Second pass: add total_length_km to features (filter short roads)
    all_features = []
    for road_ref in sorted(roads_by_ref.keys()):
        features = roads_by_ref[road_ref]
        total_length = ref_to_total_length.get(road_ref, 0)
        if total_length >= MIN_TOTAL_LENGTH_KM:
            for feature in features:
                feature["properties"]["total_length_km"] = round(total_length, 3)
                all_features.append(feature)

    feature_collection = {"type": "FeatureCollection", "features": all_features}

    with open(filepath, "w") as f:
        json.dump(feature_collection, f)

    print(f"Wrote {len(all_features)} features to {filepath}")

    # Filter metadata to only include roads meeting minimum length
    filtered_metadata = [
        meta
        for meta in metadata_list
        if ref_to_total_length.get(meta["ref"], 0) >= MIN_TOTAL_LENGTH_KM
    ]
    return filtered_metadata


def create_index(metadata_list: List[dict], output_dir: Path):
    """Create index.json with grouped variants under parent roads."""
    index_path = output_dir / "index.json"

    main_roads = {}
    variants_by_parent = defaultdict(list)

    for meta in metadata_list:
        if meta["is_variant"]:
            parent = meta["variant_of"]
            variants_by_parent[parent].append(
                {
                    "ref": meta["ref"],
                    "length_km": meta["length_km"],
                    "is_variant": True,
                    "variant_of": parent,
                    "bounds": meta["bounds"],
                }
            )
        else:
            main_roads[meta["ref"]] = {
                "ref": meta["ref"],
                "length_km": meta["length_km"],
                "is_variant": False,
                "bounds": meta["bounds"],
                "variants": [],
            }

    # Sort and assign variants
    def sort_variant_key(item):
        match = re.match(r"\d+-[DM]\d+([A-Z]{1,3})", item["ref"])
        if match:
            v = match.group(1)
            return (0, v) if len(v) == 1 else (1, v)
        return (999, item["ref"])

    for parent_ref, variants in variants_by_parent.items():
        variants.sort(key=sort_variant_key)
        if parent_ref in main_roads:
            main_roads[parent_ref]["variants"] = variants

    # Sort main roads by département then number (D-roads first, then M-roads)
    def sort_main_key(item):
        match = re.match(r"(\d+)-([DM])(\d+)", item["ref"])
        if match:
            dept = int(match.group(1))
            road_type = 0 if match.group(2) == "D" else 1  # D before M
            road_num = int(match.group(3))
            return (dept, road_type, road_num)
        return (999999, 999, 999999)

    roads_list = sorted(main_roads.values(), key=sort_main_key)

    # Count per département
    dept_counts = defaultdict(int)
    for meta in metadata_list:
        match = re.match(r"(\d+)-[DM]", meta["ref"])
        if match:
            dept_counts[match.group(1)] += 1

    index_data = {
        "total_roads": len(metadata_list),
        "main_roads": len(main_roads),
        "variant_roads": sum(len(v["variants"]) for v in main_roads.values()),
        "departements": dict(sorted(dept_counts.items())),
        "roads": roads_list,
    }

    with open(index_path, "w") as f:
        json.dump(index_data, f, indent=2)

    print(f"Created index: {index_path}")
    print(f"  Main roads: {len(main_roads)}")
    print(f"  Variant roads: {index_data['variant_roads']}")
    print(f"  Roads per département:")
    for dept, count in sorted(dept_counts.items()):
        print(f"    {dept}: {count} roads")


def main():
    project_dir = Path(__file__).parent.parent
    # pbf_file = project_dir / "osm" / "pays-de-la-loire-251206.osm.pbf"
    pbf_file = project_dir / "osm" / "france-251206.osm.pbf"
    depts_file = project_dir / "osm" / "departements.geojson"
    output_dir = project_dir / "data"

    if not pbf_file.exists():
        print(f"Error: OSM file not found: {pbf_file}")
        return

    if not depts_file.exists():
        print(f"Error: Départements file not found: {depts_file}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Clear existing files
    print("Clearing existing data files...")
    roads_file = output_dir / "roads.geojson"
    if roads_file.exists():
        roads_file.unlink()
    index_file = output_dir / "index.json"
    if index_file.exists():
        index_file.unlink()

    # Load département boundaries from GeoJSON
    departements = load_departements(depts_file)
    print(f"Loaded {len(departements)} département boundaries")

    # Extract roads using pyosmium
    roads_by_ref = extract_roads(pbf_file, departements)

    if not roads_by_ref:
        print("No départementales roads found!")
        return

    # Write single GeoJSON file with all roads
    print(f"\nWriting roads.geojson with {len(roads_by_ref)} road references...")
    metadata_list = write_all_roads_geojson(roads_by_ref, output_dir)

    # Create index for metadata
    create_index(metadata_list, output_dir)

    # Summary
    print("\n" + "=" * 60)
    print("Extraction complete!")

    main_roads = [m for m in metadata_list if not m["is_variant"]]
    variant_roads = [m for m in metadata_list if m["is_variant"]]

    print(f"Total roads: {len(metadata_list)}")
    print(f"  Main roads: {len(main_roads)}")
    print(f"  Variants: {len(variant_roads)}")
    print(f"Output: {output_dir}")

    roads_file = output_dir / "roads.geojson"
    print(f"roads.geojson size: {roads_file.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
