#!/usr/bin/env python3
"""
Extract D-roads (Départementales) from IGN RTE 500 GeoJSONL file.

Two-pass processing:
1. Stream input → SQLite index (memory efficient)
2. Query SQLite → Stream output to roads.geojsonl

Outputs roads.geojsonl (one feature per line) and index.json for the web viewer.
"""

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional

import shapely
from shapely.geometry import shape, MultiLineString

# Minimum total length (main + variants) to include a road
MIN_TOTAL_LENGTH_KM = 10


def load_departements(geojson_path: Path) -> tuple[Dict[str, any], Dict[str, str], Dict[str, list]]:
    """Load département boundaries, names, and bounds from GeoJSON file."""
    print(f"Loading département boundaries from {geojson_path}...")

    with open(geojson_path) as f:
        data = json.load(f)

    geometries = {}
    names = {}
    bounds = {}
    for feature in data.get("features", []):
        code = feature.get("properties", {}).get("code")
        geometry = shape(feature["geometry"])
        geometries[code] = geometry
        nom = feature.get("properties", {}).get("nom", "")
        names[code] = nom
        bounds[code] = list(geometry.bounds)  # [minx, miny, maxx, maxy]
        print(f"  Loaded {code} - {nom}")

    return geometries, names, bounds


def find_departement(geometry, departements: Dict[str, any]) -> Optional[str]:
    """Find which département a road geometry belongs to."""
    if not departements or geometry is None:
        return None

    try:
        best_dept = None
        best_length = 0.0

        for dept_code, dept_geom in departements.items():
            if dept_geom.contains(geometry):
                return dept_code

            if dept_geom.intersects(geometry):
                intersection = geometry.intersection(dept_geom)
                if not intersection.is_empty:
                    length = intersection.length
                    if length > best_length:
                        best_length = length
                        best_dept = dept_code

        return best_dept
    except Exception:
        return None


def parse_road_ref(num_route: str, dept_code: str) -> tuple[str, str]:
    """Parse road reference into prefixed ref, variant detection, and parent ref."""
    match = re.match(r"^(D\d+)([A-Z]{1,5})?$", num_route, re.IGNORECASE)
    if match:
        full_name = f"{dept_code}-{num_route.upper()}"
        base = match.group(1).upper()
        base_name = f"{dept_code}-{base}"
        return full_name, base_name

    full_name = f"{dept_code}-{num_route.upper()}"
    return full_name, full_name


def create_database(db_path: Path) -> sqlite3.Connection:
    """Create SQLite database with schema."""
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE segments (
            id TEXT,
            base_name TEXT,
            full_name TEXT,
            length_km REAL,
            geometry TEXT
        )
    """)
    conn.execute("CREATE INDEX idx_base_name ON segments(base_name)")
    return conn


def pass1_index(geojsonl_path: Path, conn: sqlite3.Connection, departements: Dict):
    """Stream GeoJSONL, filter départementales, insert into SQLite."""
    print(f"Pass 1: Indexing {geojsonl_path}...")

    processed = 0
    inserted = 0

    with open(geojsonl_path) as f:
        for line in f:
            if not line.strip():
                continue

            processed += 1
            if processed % 5000 == 0:
                print(f"  Processed {processed} features, inserted {inserted}...")

            feature = json.loads(line)
            props = feature.get("properties", {})

            # Filter: Départementale with NUM_ROUTE
            if props.get("CLASS_ADM") != "Départementale":
                continue
            if not props.get("NUM_ROUTE"):
                continue

            # Detect département from geometry
            try:
                geom = shape(feature["geometry"])
                if geom.is_empty:
                    continue
            except Exception:
                continue

            dept_code = find_departement(geom, departements)
            if not dept_code:
                continue

            # Parse ref
            full_name, base_name = parse_road_ref(
                props["NUM_ROUTE"], dept_code
            )

            id_rte500 = props["ID_RTE500"]

            # Insert
            conn.execute(
                """INSERT INTO segments
                   (id, base_name, full_name, length_km, geometry)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    id_rte500,
                    base_name,
                    full_name,
                    props.get("LONGUEUR", 0),
                    json.dumps(feature["geometry"]),
                ),
            )
            inserted += 1

    conn.commit()
    print(f"  Indexed {inserted} départementales from {processed} features")
    return inserted


def pass2_output(conn: sqlite3.Connection, output_dir: Path):
    """Query SQLite, compute totals, stream output to roads.geojsonl."""
    print("Pass 2: Generating output...")

    # Stream output to roads.geojsonl
    geojsonl_path = output_dir / "roads.geojsonl"
    metadata_list = []
    written_features = 0
    geom_id = 0

    with open(geojsonl_path, "w") as out:

        cur = conn.cursor()
        for row in cur.execute("SELECT distinct base_name FROM segments ORDER BY base_name"):
            base_name = row[0]
            total_length = 0
            cur2 = conn.cursor()
            for segment in cur2.execute("SELECT length_km FROM segments WHERE base_name = ?",
                                        (base_name,)):
                total_length += segment[0]

            if total_length < MIN_TOTAL_LENGTH_KM:
                continue

            geometries = []
            for segment in cur2.execute("SELECT geometry FROM segments WHERE base_name = ?",
                                        (base_name,)):
                geom = shape(json.loads(segment[0]))
                geometries.append(geom)
            all_lines = []
            for geom in geometries:
                if geom.geom_type == 'MultiLineString':
                    all_lines.extend(geom.geoms)
                elif geom.geom_type == 'LineString':
                    all_lines.append(geom)

            geometry = MultiLineString(all_lines)
            minx, miny, maxx, maxy = geometry.bounds

            feature = {
                "type": "Feature",
                "properties": {
                    "id": geom_id,
                    "ref": base_name,
                    "bounds": [minx, miny, maxx, maxy],
                    "total_length_km": round(total_length, 3)
                },
                "geometry": json.loads(shapely.to_geojson(geometry))
            }
            geojson = json.dumps(feature)
            out.write(geojson + "\n")

            geom_id += 1

            metadata_list.append({
                "ref": base_name,
                "total_length_km": round(total_length, 3),
                "bounds": [minx, miny, maxx, maxy],
            })

            written_features += 1
            if written_features % 5000 == 0:
                print(f"  Written {written_features} features...")

    print(f"  Wrote {written_features} features to {geojsonl_path}")
    return metadata_list


def create_index(metadata_list: list, dept_names: Dict, dept_bounds: Dict, output_dir: Path):
    """Create index.json."""
    index_path = output_dir / "index.json"

    index_data = {
        "total_roads": len(metadata_list),
        "departements": dict(sorted(dept_names.items())),
        "dept_bounds": dict(sorted(dept_bounds.items())),
        "roads": metadata_list,
    }

    with open(index_path, "w") as f:
        json.dump(index_data, f, indent=2)

    print(f"Created index: {index_path}")
    print(f"  Main roads: {len(metadata_list)}")


def main():
    project_dir = Path(__file__).parent.parent
    routes_file = project_dir / "data" / "routes.geojsonl"
    depts_file = project_dir / "osm" / "departements.geojson"
    output_dir = project_dir / "data"
    db_path = output_dir / "roads_temp.db"

    if not routes_file.exists():
        print(f"Error: Routes file not found: {routes_file}")
        return

    if not depts_file.exists():
        print(f"Error: Départements file not found: {depts_file}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load départements
    dept_geometries, dept_names, dept_bounds = load_departements(depts_file)
    print(f"Loaded {len(dept_geometries)} départements")

    # Pass 1: Index to SQLite
    conn = create_database(db_path)
    count = pass1_index(routes_file, conn, dept_geometries)

    if count == 0:
        print("No départementales found!")
        conn.close()
        return

    # Pass 2: Generate output
    metadata_list = pass2_output(conn, output_dir)

    # Create index
    create_index(metadata_list, dept_names, dept_bounds, output_dir)

    # Cleanup
    conn.close()
    db_path.unlink()

    # Summary
    print("\n" + "=" * 60)
    print("Extraction complete!")
    print(f"Output: {output_dir}")

    geojsonl_path = output_dir / "roads.geojsonl"
    print(f"roads.geojsonl size: {geojsonl_path.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
