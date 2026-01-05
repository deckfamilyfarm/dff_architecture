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

## Git
- Install Git CLI (then `git init` in this repo).
- Keep secrets out of version control (`.env`, outputs).***
