# Routes Départementales

Interactive map visualization of departmental roads (Routes Départementales) from France, built from IGN ROUTE 500® data.

🗺️ **[Voir la carte en ligne](https://glandais.github.io/lesdeps/)**

## Quick Start

```bash
# 1. Récupérer les données sources (voir « Provenance des données »)
#    → data/routes.geojsonl et data/departements.geojson

# 2. Extraire les départementales
uv sync
uv run scripts/extract_departementales.py

# 3. Générer les tuiles vectorielles
./scripts/generate_tiles.sh

# 4. Servir le site
npx serve
```

## Provenance des données

Aucune donnée source n'est produite par ce projet : tout part de deux jeux de données
publics, transformés localement par les scripts de `scripts/`.

### 1. `data/routes.geojsonl` — réseau routier (IGN ROUTE 500®)

Source : [IGN ROUTE 500®](https://geoservices.ign.fr/route500), licence ouverte Etalab 2.0.
Millésime utilisé : **1999**, version 1.0 édition ED991
(`ROUTE500_1-0__SHP_LAMB93_FXX_1999-01-01.7z`), livré en Shapefile Lambert-93 (EPSG:2154).

Ce millésime n'est plus proposé sur cartes.gouv.fr, qui ne publie que les éditions récentes.
Il reste disponible sur le miroir
[files.opendatarchives.fr](http://files.opendatarchives.fr/professionnels.ign.fr/route500/),
qui archive tous les millésimes depuis 1999 :

```bash
curl -O http://files.opendatarchives.fr/professionnels.ign.fr/route500/ROUTE500_1-0__SHP_LAMB93_FXX_1999-01-01.7z
7z x ROUTE500_1-0__SHP_LAMB93_FXX_1999-01-01.7z
```

La couche exploitée est `TRONCON_ROUTE` (277 929 tronçons, dont 210 527 départementales
pour 356 121 km cumulés) :

```
ROUTE500/1_DONNEES_LIVRAISON_2022-12-00027/R500_1-0_SHP_LAMB93_FXX-ED991/RESEAU_ROUTIER/TRONCON_ROUTE.shp
```

Conversion en GeoJSONL WGS84 (une entité par ligne) avec GDAL :

```bash
SHP="ROUTE500_1-0__SHP_LAMB93_FXX_1999-01-01/ROUTE500"
SHP="$SHP/1_DONNEES_LIVRAISON_2022-12-00027/R500_1-0_SHP_LAMB93_FXX-ED991"
SHP="$SHP/RESEAU_ROUTIER/TRONCON_ROUTE.shp"

ogr2ogr -f GeoJSONSeq data/routes.geojsonl -t_srs EPSG:4326 -nlt MULTILINESTRING "$SHP"
```

Cette commande reproduit le `data/routes.geojsonl` versionné à l'octet près
(md5 `e254c83aa71606f33133ed69abfc8fa4`).

Attributs exploités par l'extraction : `ID_RTE500`, `NUM_ROUTE`, `CLASS_ADM`, `LONGUEUR`.

> ⚠️ Le choix du millésime n'est pas neutre : `ID_RTE500` n'existe que dans les éditions
> anciennes (il a disparu des millésimes 2010 et 2021), et le réseau décrit grossit fortement
> d'une édition à l'autre — 210 527 départementales en 1999, 230 364 en 2010 et 568 101 en
> 2021. Changer de millésime impose donc d'adapter `extract_departementales.py`.

### 2. `data/departements.geojson` — contours des départements

⚠️ **Source non identifiée avec certitude.** Le fichier a été ajouté sans trace de son
origine (commit `a172b0d`) et ne correspond à aucun des jeux de données testés :
[france-geojson](https://github.com/gregoiredavid/france-geojson) (versions complète et
simplifiée), les [exports OSM de data.gouv](https://www.data.gouv.fr/datasets/contours-des-departements-francais-issus-d-openstreetmap)
(2014 simplifiés 50 m / 100 m, 2018) et `georef-france-departement` d'OpenDataSoft — moins de
3 % de sommets communs dans chaque cas.

Caractéristiques du fichier versionné, pour comparaison :

- 96 features, les départements de France métropolitaine (Corse `2A`/`2B` incluse), sans DROM
- propriétés `code` et `nom` uniquement, `geometry` sérialisé avant `properties`
- `Polygon` / `MultiPolygon` en WGS84, coordonnées à 12 décimales, 31 113 sommets, ~1,1 Mo
- features non triées par code

L'API Découpage administratif ne peut plus servir de substitut : elle ne renvoie plus de
contour pour les départements (le champ `contour` n'y fonctionne que pour les communes).

Pour reconstituer un fichier équivalent, [france-geojson](https://github.com/gregoiredavid/france-geojson)
expose les mêmes propriétés `code` / `nom` et est directement exploitable par
`extract_departementales.py`, au prix de contours nettement plus détaillés (donc d'une
détection de département plus lente) :

```bash
curl -o data/departements.geojson \
    https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements.geojson
```

Les contours ne servent qu'à rattacher chaque tronçon à un département : ils déterminent le
préfixe des références (`44-D17`) et les cadrages de `dept_bounds`, pas les géométries
affichées.

### 3. Fichiers calculés

| Fichier | Produit par | À partir de |
|---|---|---|
| `data/roads.geojsonl` | `scripts/extract_departementales.py` | `routes.geojsonl` + `departements.geojson` |
| `data/index.json` | `scripts/extract_departementales.py` | idem |
| `data/roads.pmtiles` | `scripts/generate_tiles.sh` (tippecanoe) | `roads.geojsonl` |

Le calcul effectué par `extract_departementales.py` :

1. Filtrage des tronçons `CLASS_ADM = "Départementale"` ayant un `NUM_ROUTE`.
2. Rattachement de chaque tronçon à un département par intersection géométrique
   (le département couvrant la plus grande longueur de tronçon l'emporte).
3. Regroupement par référence de base préfixée du département : `D17`, `D17A`, `D17BIS`
   d'un même département deviennent une seule route `44-D17`.
4. Somme des longueurs (`LONGUEUR`, en km) du groupe, fusion des géométries en une
   `MultiLineString` et calcul de la bounding box.
5. Exclusion des groupes de moins de `MIN_TOTAL_LENGTH_KM` = 10 km.

L'indexation intermédiaire passe par une base SQLite temporaire (`data/roads_temp.db`,
supprimée en fin de traitement) afin de traiter les ~144 Mo d'entrée en flux.

### 4. Fonds de carte (chargés à l'exécution, non stockés)

- Fond raster/vecteur : [VersaTiles](https://versatiles.org) (style `colorful`)
- Relief : [Mapterhorn](https://mapterhorn.com)

## Features

- Interactive MapLibre GL JS map with vector tiles
- Fast rendering with PMTiles (single file, no tile server needed)
- Road selection via dropdown or map click
- Automatic variant highlighting (D17 → D17A, D17BIS)
- Statistics panel with road lengths
- Responsive design for mobile and desktop

## Data Pipeline

### Requirements

- Python 3.9+ (`uv`)
- shapely 2.0.0+
- pyproj 3.6.0+
- GDAL / `ogr2ogr` (conversion ROUTE 500 → GeoJSONL)
- Docker (l'image felt/tippecanoe est construite au premier run)

### Step 1: Extract Roads

```bash
uv sync
uv run scripts/extract_departementales.py
```

Outputs:
- `data/roads.geojsonl` - One feature per road family (GeoJSONL)
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
- `roads.geojsonl` is an intermediate file and can be deleted after tile generation (`index.json` reste nécessaire au site)

## Data Format

### index.json

```json
{
  "total_roads": 861,
  "departements": {"01": "Ain", "02": "Aisne"},
  "dept_bounds": {"01": [4.68, 45.61, 6.17, 46.51]},
  "roads": [
    {
      "ref": "44-D17",
      "total_length_km": 170.105,
      "bounds": [-1.85, 47.12, -1.21, 47.45]
    }
  ]
}
```

### Propriétés GeoJSON

Chaque entité de `roads.geojsonl` (une famille de route, géométrie `MultiLineString`) :

- `id` : identifiant séquentiel
- `ref` : référence préfixée du département (ex. `44-D17`, variantes incluses)
- `total_length_km` : longueur cumulée de la famille (route principale + variantes)
- `bounds` : bounding box `[minLon, minLat, maxLon, maxLat]` pour le zoom

## Project Structure

```
lesdeps/
├── index.html              # Web application
├── css/style.css           # Styles
├── js/app.js               # MapLibre GL JS application
├── data/                   # Generated files
│   ├── routes.geojsonl     # IGN ROUTE 500 converti (source)
│   ├── roads.geojsonl      # Départementales extraites (intermédiaire)
│   ├── roads.pmtiles       # Vector tiles (required for web app)
│   ├── index.json          # Metadata for UI (required for web app)
│   └── departements.geojson # Département boundaries (defines extraction scope)
├── scripts/
│   ├── extract_departementales.py  # Extraction des départementales depuis ROUTE 500
│   └── generate_tiles.sh           # Generate PMTiles
└── pyproject.toml
```

## Usage Examples

### Query roads with jq

```bash
# List all roads in département 44
jq '.roads[] | select(.ref | startswith("44-"))' data/index.json

# Find roads longer than 100 km
jq '.roads[] | select(.total_length_km > 100) | .ref' data/index.json

# Count roads per département
jq '.departements' data/index.json
```

### Load road data in Python

```python
import json

# roads.geojsonl : une Feature par ligne
with open('data/roads.geojsonl') as f:
    roads = [json.loads(line) for line in f if line.strip()]

d17 = next(r for r in roads if r['properties']['ref'] == '44-D17')
print(f"{d17['properties']['ref']}: {d17['properties']['total_length_km']} km")
```

## License

Données routières et contours administratifs © IGN — [Licence Ouverte Etalab 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/).
Fonds de carte © VersaTiles / OpenStreetMap contributors (ODbL) et Mapterhorn.
