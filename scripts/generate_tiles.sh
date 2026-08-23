#!/bin/bash
# Generate PMTiles from GeoJSON using felt/tippecanoe (https://github.com/felt/tippecanoe)
#
# felt/tippecanoe is the maintained fork of mapbox/tippecanoe.
# No official image is published, so the image is built from the repo on first run.
# Override the version with TIPPECANOE_VERSION=2.79.0 ./scripts/generate_tiles.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"

TIPPECANOE_VERSION="${TIPPECANOE_VERSION:-2.79.0}"
IMAGE="felt-tippecanoe:${TIPPECANOE_VERSION}"

# Check input file exists
if [ ! -f "$DATA_DIR/roads.geojsonl" ]; then
    echo "Error: roads.geojsonl not found in $DATA_DIR"
    echo "Run: uv run scripts/extract_departementales.py first"
    exit 1
fi

# Build the image once from scripts/tippecanoe/Dockerfile
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Building $IMAGE from felt/tippecanoe..."
    docker build -t "$IMAGE" --build-arg "TIPPECANOE_VERSION=${TIPPECANOE_VERSION}" "$SCRIPT_DIR/tippecanoe"
fi

echo "Generating PMTiles from roads.geojsonl..."

docker run --rm \
    -v "$DATA_DIR:/data" \
    "$IMAGE" \
    tippecanoe \
    -o /data/roads.pmtiles \
    -l roads \
    -zg \
    --drop-densest-as-needed \
    --force \
    -P \
    /data/roads.geojsonl

echo ""
echo "Done! Output: $DATA_DIR/roads.pmtiles"
ls -lh "$DATA_DIR/roads.pmtiles"
