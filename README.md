# Routes Départementales

Interactive map visualization of departmental roads (Routes Départementales) from France.

🗺️ **[Voir la carte en ligne](https://glandais.github.io/lesdeps/)**

## Quick Start

```bash
# 1. Download OSM data and configure
# - Place .osm.pbf file in osm/ directory
# - Edit pbf_file path in scripts/extract_departementales.py

# 2. Extract roads from OSM
uv sync
uv run scripts/extract_departementales.py

# 3. Generate vector tiles
./scripts/generate_tiles.sh

# 4. Serve
npx serve
```

## Features

- Interactive MapLibre GL JS map with vector tiles
- Fast rendering with PMTiles (single file, no tile server needed)
- Road selection via dropdown or map click
- Automatic variant highlighting (D17 → D17A, D17BIS)
- Statistics panel with road lengths
- Responsive design for mobile and desktop

## Data Pipeline

### Requirements

- Python 3.9+
- osmium 4.2.0+
- shapely 2.0.0+
- pyproj 3.6.0+
- Docker (l'image felt/tippecanoe est construite au premier run)

### Step 1: Extract Roads

```bash
uv sync
uv run scripts/extract_departementales.py
```

Outputs:
- `data/roads.geojson` - All road segments in one file
- `data/index.json` - Metadata for UI (dropdown, statistics)

### Step 2: Generate Tiles

```bash
./scripts/generate_tiles.sh
```

Builds felt/tippecanoe (`scripts/tippecanoe/Dockerfile`) and creates `data/roads.pmtiles`.

### Output

- Roads extracted from all départements defined in `data/departements.geojson`
- Main roads + variants (e.g., D17 → D17A, D17BIS)
- Single PMTiles file for efficient vector tile serving
- Intermediate files (`roads.geojson`, `index.json`) can be deleted after tile generation

## Data Format

### index.json

Roads are organized with variants nested under parent roads:

```json
{
  "total_roads": 861,
  "main_roads": 601,
  "variant_roads": 260,
  "departements": {"44": 150, "49": 120},
  "roads": [
    {
      "ref": "44-D17",
      "length_km": 170.105,
      "is_variant": false,
      "bounds": [-1.85, 47.12, -1.21, 47.45],
      "variants": [
        {
          "ref": "44-D17A",
          "length_km": 5.2,
          "is_variant": true,
          "variant_of": "44-D17",
          "bounds": [-1.52, 47.28, -1.48, 47.31]
        }
      ]
    }
  ]
}
```

### GeoJSON Properties

Each road segment in `roads.geojson` includes:

- `ref`: Road reference with département prefix (e.g., "44-D17")
- `dept`: Département code
- `variant`: Variant suffix if present (A, BIS, TER)
- `is_variant`: Boolean indicating variant status
- `parent_ref`: Parent road reference if variant
- `length_km`: Segment length in kilometers
- `total_length_km`: Combined length of road family (main + variants), used for color gradient

## Project Structure

```
lesdeps/
├── index.html              # Web application
├── css/style.css           # Styles
├── js/app.js               # MapLibre GL JS application
├── data/                   # Generated files
│   ├── roads.geojson       # All road segments (intermediate)
│   ├── roads.pmtiles       # Vector tiles (required for web app)
│   ├── index.json          # Metadata for UI (required for web app)
│   └── departements.geojson # Département boundaries (defines extraction scope)
├── scripts/
│   ├── extract_departementales.py  # Extract roads from OSM
│   └── generate_tiles.sh           # Generate PMTiles
└── pyproject.toml
```

## Usage Examples

### Query roads with jq

```bash
# List all roads in département 44
jq '.roads[] | select(.ref | startswith("44-"))' data/index.json

# Find roads longer than 100 km
jq '.roads[] | select(.length_km > 100) | .ref' data/index.json

# Count roads per département
jq '.departements' data/index.json
```

### Load road data in Python

```python
import json

with open('data/roads.geojson') as f:
    roads = json.load(f)

# Filter for a specific road
d17_segments = [f for f in roads['features'] if f['properties']['ref'] == '44-D17']
print(f"Road D17 has {len(d17_segments)} segments")
```

## License

OSM data is © OpenStreetMap contributors, available under ODbL.
