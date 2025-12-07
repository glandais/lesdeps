#!/bin/bash
# Generate PMTiles from GeoJSON using Tippecanoe Docker image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"

# Check input file exists
if [ ! -f "$DATA_DIR/roads.geojson" ]; then
    echo "Error: roads.geojson not found in $DATA_DIR"
    echo "Run: uv run scripts/extract_departementales.py first"
    exit 1
fi

echo "Generating PMTiles from roads.geojson..."

# Generate PMTiles directly with Tippecanoe
docker run --rm \
    -v "$DATA_DIR:/data" \
    tippecanoe:latest \
    tippecanoe \
    -o /data/roads.pmtiles \
    -l roads \
    -zg \
    --drop-densest-as-needed \
    --force \
    /data/roads.geojson

echo ""
echo "Done! Output: $DATA_DIR/roads.pmtiles"
ls -lh "$DATA_DIR/roads.pmtiles"
