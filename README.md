# QGIS + FreeCAD Python scaffold

Python starter to render maps from QGIS data (project or direct layers with YAML styling) and to drive FreeCAD for simple 3D extrusions.

## Setup (Windows)
- Use the OSGeo/QGIS Python (so bindings work): `C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\Python312\python.exe`.
- Install FreeCAD (for `FreeCAD` Python module).
- Copy `.env.example` to `.env` and fill values (keep `.env` untracked).
- Install deps:
  ```powershell
  C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\Python312\python.exe -m pip install -r requirements.txt
  ```

## Setup (macOS)
- Install QGIS and FreeCAD (app bundles from their official installers).
- Use the QGIS Python (so bindings work): `/Applications/QGIS.app/Contents/MacOS/bin/python3`.
- Copy `.env.example` to `.env` and fill values (keep `.env` untracked).
- Install deps:
  ```bash
  /Applications/QGIS.app/Contents/MacOS/bin/python3 -m pip install -r requirements.txt
  ```

## .env keys
- `QGIS_PROJECT_DIR` – folder with your data or project.
- `QGIS_PROJECT_FILE` – project filename; leave blank to load layers directly.
- `SUBJECT_LAYER_NAME` – layer to render if no project file (filename or stem).
- `SUBJECT_ID_FIELD` / `SUBJECT_ID_VALUE` – optional attribute filter.
- `OUTPUT_DIR` – where rendered maps/models are written.
- `QGIS_PREFIX_PATH` – QGIS install prefix (e.g., `C:/Users/jacob/AppData/Local/Programs/OSGeo4W/apps/qgis`).
- `FREECAD_LIBRARY_DIR` – path that contains `FreeCAD.pyd`/`FreeCAD.dll` (e.g., `C:/Program Files/FreeCAD 1.0/bin`).
- `OGR2OGR_PATH` – optional explicit path to `ogr2ogr` (otherwise uses PATH/QGIS).
- `GDAL_DATA` – optional path to GDAL data (otherwise inferred from QGIS).
- `CONTOUR_SHP_PATH` – optional default contour shapefile for DXF export.
- `CONTOUR_DXF_PATH` – optional default DXF output path.
- `CONTOUR_Z_FIELD` – elevation field name (default `Contour`).
- `OUTPUT_CONTOUR_INTERVAL` – optional contour interval (e.g., `1` for 1' spacing).
- `OUTPUT_MERGE_FRAGMENTS` – optional boolean to merge line fragments per contour value.
- `IMAGERY_PROVIDER` – imagery source (`wms` or `xyz`).
- `WMS_URL` / `WMS_LAYERS` – WMS endpoint and layer id(s) for imagery export.
- `WMS_FORMAT` – WMS image format (default `image/jpeg`).
- `WMS_CRS` – optional CRS for WMS requests (e.g., `EPSG:3857`).
- `XYZ_URL` – XYZ tile URL template.
- `XYZ_ZMIN` / `XYZ_ZMAX` – zoom range for XYZ tiles.
- `XYZ_CRS` – XYZ CRS (default `EPSG:3857`).
- `SITE_BOUNDARY_PATH` – boundary layer path for clipping imagery (relative to `QGIS_PROJECT_DIR`).
- `SITE_BOUNDARY_LAYER` – boundary layer name if loading from a QGIS project.
- `IMAGERY_TIF_PATH` – output GeoTIFF path.
- `GDALWARP_PATH` – optional explicit path to `gdalwarp`.
- `OUTPUT_QGIS_PROJECT_PATH` – output QGIS project path.
- `OUTPUT_DEM_TIF_PATH` – optional DEM GeoTIFF to include in the project.
- `DEM_PIXEL_SIZE` – DEM resolution in map units (default `1.0`).
- `EXTRA_LAYERS` – comma-separated list of extra layers to include.

## Run commands
- Render map with config:
  ```powershell
  C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\Python312\python.exe -m src.main render-map --width 1600 --height 1200 --config configs/map1.yaml
  ```
- Build 3D extrusion (sample footprint in code):
  ```powershell
  C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\Python312\python.exe -m src.main build-3d --height 6 --fmt step
  ```
- Export 3D DXF from contours:
  ```bash
  python -m src.main export-dxf --input "/path/to/contours.shp" --output "/path/to/contours_3d.dxf" --z-field Contour
  ```
  - Optional filters:
    - `--output-contour-interval 1` keeps only contours at 1' spacing (or any interval).
    - `--merge-fragments` merges line fragments per contour value.
  - If flags are omitted, defaults can come from `OUTPUT_CONTOUR_INTERVAL` and `OUTPUT_MERGE_FRAGMENTS` in `.env`.
  - Use `--force` to regenerate even if output exists.
- Export WMS imagery as GeoTIFF clipped to boundary:
  ```bash
  python -m src.main export-imagery --width 4096 --height 4096
  ```
  - Uses `WMS_URL`/`WMS_LAYERS` and clips to `SITE_BOUNDARY_PATH` or `SITE_BOUNDARY_LAYER`.
  - Use `--force` to regenerate even if output exists.
- Export a QGIS project that includes contours, imagery, boundary, and optional DEM:
  ```bash
  python -m src.main export-qgis-project
  ```
  - If no DEM exists yet, it is generated from contours using `CONTOUR_Z_FIELD`.
  - Use `--force` to regenerate even if output exists.
- Export everything in one command:
  ```bash
  python -m src.main export-all --width 4096 --height 4096
  ```
  - Uses `.env` for all paths and skips outputs that already exist unless `--force` is provided.

## Map configs (YAML)
- Define layers (vector/raster/WMS), styling, extent layer, legend, and north arrow in `configs/*.yaml`.
- Example (`configs/map1.yaml`):
  - `site_boundary` with red outline/transparent fill.
  - `six_inch_contours_ground_UTM10N` with brown lines.
  - Base WMS (BlueMarble) behind other layers.

## Files to know
- `src/qgis_map.py` – QGIS bootstrap, layer loading (project or paths/WMS), styling, legend/north arrow, export PNG.
- `src/freecad_model.py` – build solid from footprint, export STEP/OBJ.
- `src/main.py` – CLI entrypoints for maps and FreeCAD.
- `.env.example` – template for environment settings.
- `.gitignore` – ignores `.env`, `output/`, venvs, caches.
- `AGENT.md` – quick notes for agents/contributors.

## Topography workflow (QGIS contours -> Rhino NURBS)
This documents how we built a 3D topo from 6" contours and imported into Rhino.

1) Source contours (shapefile with elevation field):
   - `C:\Deck Family Farm\HOUSE\Site\GIS\six_inch_contours_ground_UTM10N.shp`
   - Elevation field: `Contour` (values in feet, 0.5 ft = 6" interval).

2) Export 3D DXF with Z values:
   ```bash
   python -m src.main export-dxf --input "/path/to/six_inch_contours_ground_UTM10N.shp" \
     --output "/path/to/six_inch_contours_ground_UTM10N_3d.dxf" --z-field Contour --output-contour-interval 1 --merge-fragments
   ```
   - If `ogr2ogr` is not on PATH, set `OGR2OGR_PATH` in `.env` (Windows OSGeo4W example: `C:/OSGeo4W/bin/ogr2ogr.exe`).
   - If `GDAL_DATA` is not set, it is inferred from `QGIS_PREFIX_PATH` (macOS QGIS example: `/Applications/QGIS.app/Contents/MacOS`).

3) Rhino import and scale:
   - Import the DXF.
   - XY is UTM meters, Z is feet. Keep Rhino model units in feet.
   - Scale XY by 3.28084 (meters -> feet), keep Z unchanged:
     ```
     _Scale2D _Pause _Factor 3.28084 _Enter
     ```

4) Optional cleanup:
   - Delete every other contour to get 1 ft spacing:
     ```python
     # -*- coding: utf-8 -*-
     import rhinoscriptsyntax as rs
     ids = rs.GetObjects("Select contour curves", rs.filter.curve, preselect=True)
     if ids:
         to_delete = []
         for cid in ids:
             z = rs.CurveStartPoint(cid).Z
             if abs(z - round(z)) > 1e-6:
                 to_delete.append(cid)
         rs.DeleteObjects(to_delete)
     ```
   - Reduce point count for polylines: `ReducePolyline` (start with 0.05 ft tolerance).

5) Build NURBS surface:
   - Draw a boundary curve around the site.
   - Select contours + boundary.
   - Run `Patch` with `Trim=Yes`.

## Git
- Install Git CLI (then `git init` in this repo).
- Keep secrets out of version control (`.env`, outputs).***
