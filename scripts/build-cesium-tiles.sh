#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/output"
TERRAIN_DIR="${OUTPUT_DIR}/terrain"
IMAGERY_DIR="${OUTPUT_DIR}/imagery"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

DEM_TIF="${OUTPUT_DEM_TIF_PATH:-${OUTPUT_DIR}/site_dem.tif}"
IMAGERY_TIF="${IMAGERY_TIF_PATH:-${OUTPUT_DIR}/site_imagery.tif}"

mkdir -p "${TERRAIN_DIR}" "${IMAGERY_DIR}"

if [[ ! -f "${DEM_TIF}" ]]; then
  echo "DEM not found: ${DEM_TIF}" >&2
  exit 1
fi

if [[ ! -f "${IMAGERY_TIF}" ]]; then
  echo "Imagery not found: ${IMAGERY_TIF}" >&2
  exit 1
fi

if command -v ctb-tile >/dev/null 2>&1; then
  echo "Building terrain tiles..."
  ctb-tile -f Mesh -o "${TERRAIN_DIR}" "${DEM_TIF}"
else
  if ! command -v gdalwarp >/dev/null 2>&1; then
    echo "gdalwarp not found on PATH. Install GDAL or use QGIS GDAL scripts." >&2
    exit 1
  fi
  if ! command -v gdal_translate >/dev/null 2>&1; then
    echo "gdal_translate not found on PATH. Install GDAL or use QGIS GDAL scripts." >&2
    exit 1
  fi
  if ! command -v gdalinfo >/dev/null 2>&1; then
    echo "gdalinfo not found on PATH. Install GDAL or use QGIS GDAL scripts." >&2
    exit 1
  fi
  echo "ctb-tile not found; building single-tile heightmap terrain..."
  TMP_TIF="${TERRAIN_DIR}/heightmap_wgs84.tif"
  HEIGHTMAP_PNG="${TERRAIN_DIR}/heightmap.png"
  HEIGHTMAP_JSON="${TERRAIN_DIR}/heightmap.json"
  gdalwarp -t_srs EPSG:4326 -r bilinear -dstnodata -9999 -overwrite "${DEM_TIF}" "${TMP_TIF}"
  if [[ -n "${HEIGHTMAP_MAX_SIZE:-}" ]]; then
    RESAMPLED_TIF="${TERRAIN_DIR}/heightmap_wgs84_resampled.tif"
    gdal_translate -outsize "${HEIGHTMAP_MAX_SIZE}" "${HEIGHTMAP_MAX_SIZE}" -r bilinear "${TMP_TIF}" "${RESAMPLED_TIF}"
    TMP_TIF="${RESAMPLED_TIF}"
  fi
  read -r MINVAL MAXVAL WIDTH HEIGHT WEST SOUTH EAST NORTH <<EOF
$(python3 - "${TMP_TIF}" <<'PY'
import json, subprocess, sys
path = sys.argv[1]
info = json.loads(subprocess.check_output(["gdalinfo", "-json", "-mm", path], text=True))
band = info["bands"][0]
minv = band.get("minimum")
maxv = band.get("maximum")
if minv is None or maxv is None:
    stats = band.get("stats", {})
    minv = stats.get("minimum", 0.0)
    maxv = stats.get("maximum", 0.0)
size = info.get("size", [0, 0])
extent = info.get("wgs84Extent") or {}
coords = extent.get("coordinates")
if coords:
    lons = [pt[0] for ring in coords for pt in ring]
    lats = [pt[1] for ring in coords for pt in ring]
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)
else:
    west = south = east = north = 0.0
if minv == maxv:
    minv = minv if minv is not None else 0.0
    maxv = minv + 1.0
print(minv, maxv, size[0], size[1], west, south, east, north)
PY
)
EOF
  gdal_translate -of PNG -ot Byte -scale "${MINVAL}" "${MAXVAL}" 0 255 "${TMP_TIF}" "${HEIGHTMAP_PNG}"
  python3 - <<PY
import json
minv = float("${MINVAL}")
maxv = float("${MAXVAL}")
data = {
    "width": int("${WIDTH}"),
    "height": int("${HEIGHT}"),
    "west": float("${WEST}"),
    "south": float("${SOUTH}"),
    "east": float("${EAST}"),
    "north": float("${NORTH}"),
    "heightOffset": minv,
    "heightScale": (maxv - minv) / 255.0 if maxv != minv else 1.0,
}
with open("${HEIGHTMAP_JSON}", "w", encoding="utf-8") as f:
    json.dump(data, f)
PY
  echo "Heightmap terrain written to ${HEIGHTMAP_PNG}"
fi

if ! command -v gdal2tiles.py >/dev/null 2>&1; then
  echo "gdal2tiles.py not found on PATH. Install GDAL or use QGIS GDAL scripts." >&2
  exit 1
fi

echo "Building imagery tiles..."
if ! command -v gdalwarp >/dev/null 2>&1; then
  echo "gdalwarp not found on PATH. Install GDAL or use QGIS GDAL scripts." >&2
  exit 1
fi
IMAGERY_MERC_TIF="${IMAGERY_DIR}/_imagery_3857.tif"
gdalwarp -t_srs EPSG:3857 -r bilinear -overwrite "${IMAGERY_TIF}" "${IMAGERY_MERC_TIF}"
IMAGERY_TIF_FOR_TILES="${IMAGERY_MERC_TIF}"
gdal2tiles.py --xyz -w none -r bilinear -s EPSG:3857 -p mercator "${IMAGERY_TIF_FOR_TILES}" "${IMAGERY_DIR}"

ROOT_DIR="${ROOT_DIR}" IMAGERY_TIF_FOR_TILES="${IMAGERY_TIF_FOR_TILES}" python3 - <<'PY'
import json
import os
import subprocess
import sys

root_dir = os.environ.get("ROOT_DIR") or os.getcwd()
imagery_tif = os.environ.get("IMAGERY_TIF_FOR_TILES") or os.environ.get("IMAGERY_TIF_PATH") or os.path.join(root_dir, "output", "site_imagery.tif")
imagery_dir = os.path.join(root_dir, "output", "imagery")
imagery_srs = os.environ.get("IMAGERY_TIF_SRS") or "EPSG:3857"
imagery_tif = os.path.abspath(imagery_tif)
imagery_dir = os.path.abspath(imagery_dir)

def valid_latlon(w, s, e, n):
    return all(
        [
            isinstance(w, (int, float)),
            isinstance(s, (int, float)),
            isinstance(e, (int, float)),
            isinstance(n, (int, float)),
            -180.0 <= w <= 180.0,
            -180.0 <= e <= 180.0,
            -90.0 <= s <= 90.0,
            -90.0 <= n <= 90.0,
        ]
    )

def transform_bbox(info):
    corners = info.get("cornerCoordinates") or {}
    points = [
        corners.get("upperLeft"),
        corners.get("upperRight"),
        corners.get("lowerLeft"),
        corners.get("lowerRight"),
    ]
    points = [p for p in points if p and len(p) >= 2]
    if not points:
        return None
    try:
        srs = imagery_srs
        if not srs:
            srs = subprocess.check_output(["gdalsrsinfo", "-o", "epsg", imagery_tif], text=True).strip()
        if not srs:
            return None
        inp = "\n".join(f"{p[0]} {p[1]}" for p in points).encode()
        out = subprocess.check_output(
            ["gdaltransform", "-s_srs", srs, "-t_srs", "EPSG:4326"],
            input=inp,
        ).decode()
        lons = []
        lats = []
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                lons.append(float(parts[0]))
                lats.append(float(parts[1]))
        if lons and lats:
            return min(lons), min(lats), max(lons), max(lats)
    except Exception:
        return None
    return None

try:
    info = json.loads(subprocess.check_output(["gdalinfo", "-json", imagery_tif], text=True))
    extent = info.get("wgs84Extent") or {}
    coords = extent.get("coordinates") or []
    if coords:
        lons = [pt[0] for ring in coords for pt in ring]
        lats = [pt[1] for ring in coords for pt in ring]
        west, east = min(lons), max(lons)
        south, north = min(lats), max(lats)
    else:
        west = south = east = north = 0.0
    if not valid_latlon(west, south, east, north):
        transformed = transform_bbox(info)
        if transformed:
            west, south, east, north = transformed
except Exception:
    west = south = east = north = 0.0

zooms = []
if os.path.isdir(imagery_dir):
    for name in os.listdir(imagery_dir):
        if name.isdigit():
            zooms.append(int(name))
if zooms:
    min_zoom = min(zooms)
    max_zoom = max(zooms)
else:
    min_zoom = 0
    max_zoom = 18

meta = {
    "west": west,
    "south": south,
    "east": east,
    "north": north,
    "minZoom": min_zoom,
    "maxZoom": max_zoom,
}

out_path = os.path.join(imagery_dir, "tiles.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(meta, f)
print(f"Wrote imagery metadata: {out_path}")
PY

rm -f "${IMAGERY_MERC_TIF}"

echo "Done. Terrain: ${TERRAIN_DIR}, Imagery: ${IMAGERY_DIR}"
