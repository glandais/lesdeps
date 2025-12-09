# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Interactive map visualization of French departmental roads (Routes Départementales) extracted from OpenStreetMap data. Two main components:

1. **Data Pipeline** - Python extracts D-roads from OSM GeoJSONL → Tippecanoe generates PMTiles
2. **Web Application** - MapLibre GL JS map with vector tiles

## Commands

```bash
# Install Python dependencies
uv sync

# Extract roads from OSM data
uv run scripts/extract_departementales.py

# Generate vector tiles (requires Docker with tippecanoe:latest image)
./scripts/generate_tiles.sh

# Serve web app
npx serve
```

## Architecture

### Data Flow
```
routes.geojsonl (OSM export) + osm/departements.geojson
    ↓ extract_departementales.py
    ↓ département detection via geometry intersection
    ↓ road grouping by base ref (D1, D17 groups D17A, D17BIS)
    ↓ filter: MIN_TOTAL_LENGTH_KM = 10
    ↓
data/roads.geojsonl + data/index.json
    ↓ generate_tiles.sh (Tippecanoe via Docker)
    ↓
data/roads.pmtiles → MapLibre GL JS
```

### Road Reference System
- Roads prefixed with département code: `44-D17`, `49-D23`
- Base name groups variants: `44-D17` includes segments from `D17`, `D17A`, `D17BIS`
- Total length = sum of all segments with same base name

### Key Constants
- `MIN_TOTAL_LENGTH_KM = 10` in `extract_departementales.py`

### Data Structures

**index.json**:
```json
{
  "total_roads": 861,
  "departements": {"01": "Ain", "02": "Aisne", ...},
  "roads": [{
    "id": 1,
    "ref": "44-D17",
    "total_length_km": 170.105,
    "bounds": [minLon, minLat, maxLon, maxLat]
  }]
}
```

**roads.geojsonl** (one feature per line):
- `id`: Unique feature ID
- `base_name`: Road family (e.g., `44-D17`)
- `full_name`: Specific segment (e.g., `44-D17A`)
- `total_length_km`: Combined length of road family
- `bounds`: Bounding box for zoom

### Web App (js/app.js)

`RoadsMapApp` class:
- Loads PMTiles via `pmtiles` protocol
- Uses MapLibre style expressions for color gradient (blue→purple→red by length)
- Layer filters for road selection/highlighting
- Département names loaded from index.json (not hardcoded)
- Bounds stored in index.json for zoom (no feature queries needed)

### Python Script (scripts/extract_departementales.py)

Two-pass processing:
1. **Pass 1**: Stream GeoJSONL → SQLite index (memory efficient for large files)
2. **Pass 2**: Query SQLite by base_name → Stream output to roads.geojsonl

Key functions:
- `load_departements()`: Returns `(geometries, names)` tuple from GeoJSON
- `find_departement()`: Determines département by geometry intersection
- `parse_road_ref()`: Extracts base name and full name from road reference
