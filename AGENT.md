# AGENT NOTES

## Environment
- Use the OSGeo/QGIS Python at `C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\Python312\python.exe` so QGIS bindings work.
- `.env` holds defaults; see `.env.example` for keys. Keep real `.env` out of version control.
- Network access may be needed for WMS imagery.

## Common commands
- Render map with config:  
  `C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\Python312\python.exe -m src.main render-map --width 1600 --height 1200 --config configs/map1.yaml`
- Build FreeCAD model:  
  `C:\Users\jacob\AppData\Local\Programs\OSGeo4W\apps\Python312\python.exe -m src.main build-3d --height 6 --fmt step`

## Conventions
- Layers and styling come from YAML configs under `configs/`.
- Keep `output/` and `.env` ignored.
- Prefer `apply_patch` for edits; avoid destructive git commands.

## Git
- Initialize repo with `git init` once Git is installed on PATH.
- Commit generated files except secrets (`.env`) and outputs.
