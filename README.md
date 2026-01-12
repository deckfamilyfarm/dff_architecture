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

## .env keys
- `QGIS_PROJECT_DIR` – folder with your data or project.
- `QGIS_PROJECT_FILE` – project filename; leave blank to load layers directly.
- `SUBJECT_LAYER_NAME` – layer to render if no project file (filename or stem).
- `SUBJECT_ID_FIELD` / `SUBJECT_ID_VALUE` – optional attribute filter.
- `OUTPUT_DIR` – where rendered maps/models are written.
- `QGIS_PREFIX_PATH` – QGIS install prefix (e.g., `C:/Users/jacob/AppData/Local/Programs/OSGeo4W/apps/qgis`).
- `FREECAD_LIBRARY_DIR` – path that contains `FreeCAD.pyd`/`FreeCAD.dll` (e.g., `C:/Program Files/FreeCAD 1.0/bin`).

## Run commands
- Render map with config:
  ```powershell
  C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\Python312\python.exe -m src.main render-map --width 1600 --height 1200 --config configs/map1.yaml
  ```
- Build 3D extrusion (sample footprint in code):
  ```powershell
  C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\Python312\python.exe -m src.main build-3d --height 6 --fmt step
  ```

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
   ```powershell
   $env:GDAL_DATA = "C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\gdal\share\gdal"
   C:\Users\jacob\AppData\Local\Programs\OSGeo4W\bin\ogr2ogr.exe -f DXF `
     "C:\Deck Family Farm\HOUSE\Site\AutoCAD\six_inch_contours_ground_UTM10N_3d.dxf" `
     "C:\Deck Family Farm\HOUSE\Site\GIS\six_inch_contours_ground_UTM10N.shp" `
     -zfield Contour -nlt LINESTRING25D -skipfailures
   ```

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
