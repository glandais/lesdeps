# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Interactive map visualization of French departmental roads (Routes Départementales) extracted from OpenStreetMap data. Two main components:

1. **Data Pipeline** - Python extracts D-roads from OSM PBF → Tippecanoe generates PMTiles
2. **Web Application** - MapLibre GL JS map with vector tiles

## Commands

```bash
# Install Python dependencies
uv sync

# Extract roads from OSM data (edit pbf_file path in script first)
uv run scripts/extract_departementales.py

# Generate vector tiles (requires Docker with tippecanoe:latest image)
./scripts/generate_tiles.sh

# Serve web app
npx serve
```

## Architecture

### Data Flow
```
OSM PBF (osm/*.pbf) + departements.geojson
    ↓ pyosmium extraction (WKBFactory)
    ↓ département detection via geometry intersection
    ↓ road grouping by ref (D1, D17, D17A, etc.)
    ↓ Lambert-93 projection for accurate length (EPSG:2154)
    ↓ filter: MIN_TOTAL_LENGTH_KM = 5
    ↓
roads.geojson + index.json
    ↓ Tippecanoe (Docker)
    ↓
roads.pmtiles → MapLibre GL JS
```

### Road Reference System
- Roads prefixed with département code: `44-D17`, `49-D23`
- Variants detected automatically: `44-D17A`, `44-D17BIS`
- Total length = main road + all variants (used for filtering and coloring)

### Key Constants
- `MIN_TOTAL_LENGTH_KM = 5` - Roads with total length < 5km excluded
- `pbf_file` in `extract_departementales.py` - OSM source file path (must be set manually)

### Data Structures

**index.json**: Metadata for UI (dropdowns, statistics, bounds for zooming)
```json
{
  "roads": [{
    "ref": "44-D17",
    "length_km": 170.105,
    "bounds": [minLon, minLat, maxLon, maxLat],
    "variants": [{"ref": "44-D17A", "length_km": 5.2}]
  }]
}
```

**roads.geojson feature properties**:
- `ref`: Road reference with département prefix
- `total_length_km`: Combined length of road family (for color gradient)
- `dept`, `variant`, `is_variant`, `parent_ref`, `length_km`

### Web App (js/app.js)

`RoadsMapApp` class:
- Loads PMTiles via `pmtiles` protocol
- Uses MapLibre style expressions for color gradient (blue→purple→red by length)
- Layer filters for road selection/highlighting
- Hit area layer (12px) for easier clicking
- Bounds stored in index.json for zoom (no feature queries needed)
