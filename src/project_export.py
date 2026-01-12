import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .ogr2ogr_export import normalize_input_path
from .qgis_map import ensure_qgis, load_data_layer
from .raster_export import load_boundary_layer


def load_env(env_path: Optional[str] = None) -> dict:
    load_dotenv(dotenv_path=env_path)
    dem_tif = os.environ.get("OUTPUT_DEM_TIF_PATH") or None
    project_out = os.environ.get("OUTPUT_QGIS_PROJECT_PATH") or None
    imagery_tif = os.environ.get("IMAGERY_TIF_PATH") or None
    return {
        "project_dir": Path(os.environ["QGIS_PROJECT_DIR"]),
        "output_dir": Path(os.environ.get("OUTPUT_DIR", "./output")),
        "qgis_prefix": os.environ.get("QGIS_PREFIX_PATH"),
        "subject_layer": os.environ.get("SUBJECT_LAYER_NAME", ""),
        "contour_shp": os.environ.get("CONTOUR_SHP_PATH"),
        "imagery_tif": imagery_tif,
        "boundary_path": os.environ.get("SITE_BOUNDARY_PATH"),
        "boundary_layer": os.environ.get("SITE_BOUNDARY_LAYER"),
        "project_out": project_out,
        "dem_tif": dem_tif,
        "dem_pixel_size": os.environ.get("DEM_PIXEL_SIZE"),
        "extra_layers": os.environ.get("EXTRA_LAYERS", "BarnPolygons.shp,roads.shp"),
        "contour_z_field": os.environ.get("CONTOUR_Z_FIELD", "Contour"),
    }


def resolve_path(project_dir: Path, path_str: Optional[str]) -> Optional[Path]:
    if not path_str:
        return None
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = project_dir / candidate
    return candidate


def run_export_project(
    output_path: Optional[str] = None,
    force: bool = False,
    env_path: Optional[str] = None,
) -> Path:
    cfg = load_env(env_path)
    cfg["output_dir"].mkdir(parents=True, exist_ok=True)
    app = ensure_qgis(cfg["qgis_prefix"])

    from qgis.core import QgsProject

    project = QgsProject.instance()

    layers = []

    contour_layer = None
    contour_path = resolve_path(cfg["project_dir"], cfg.get("contour_shp"))
    if contour_path:
        contour_path = normalize_input_path(str(contour_path))
        if contour_path.exists():
            contour_layer = load_data_layer(cfg["project_dir"], str(contour_path))
            layers.append(contour_layer)

    imagery_path = resolve_path(cfg["project_dir"], cfg.get("imagery_tif"))
    if imagery_path and imagery_path.exists():
        layers.append(load_data_layer(cfg["project_dir"], str(imagery_path)))

    boundary_layer = load_boundary_layer(cfg, None)
    if boundary_layer:
        layers.append(boundary_layer)

    dem_layer = None
    dem_path = resolve_path(cfg["project_dir"], cfg.get("dem_tif"))
    if dem_path and dem_path.exists():
        dem_layer = load_data_layer(cfg["project_dir"], str(dem_path))
        layers.append(dem_layer)

    extra_layers = [s.strip() for s in cfg.get("extra_layers", "").split(",") if s.strip()]
    for extra in extra_layers:
        try:
            layers.append(load_data_layer(cfg["project_dir"], extra))
        except Exception:
            pass

    if contour_layer and not dem_layer:
        dem_layer = generate_dem_from_contours(
            contour_layer,
            boundary_layer,
            cfg,
            force=force,
        )
        if dem_layer:
            layers.append(dem_layer)

    if not layers:
        raise RuntimeError("No layers found to add to QGIS project.")

    for layer in layers:
        project.addMapLayer(layer)

    if layers and not project.crs().isValid():
        project.setCrs(layers[0].crs())

    out_path = Path(output_path or cfg.get("project_out") or (cfg["output_dir"] / "qgis_view.qgz"))
    if out_path.exists() and not force:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not project.write(str(out_path)):
        raise RuntimeError(f"Failed to write QGIS project: {out_path}")
    return out_path


def generate_dem_from_contours(contour_layer, boundary_layer, cfg: dict, force: bool = False):
    try:
        import processing
        from processing.core.Processing import Processing
        from qgis.analysis import QgsNativeAlgorithms
        from qgis.core import QgsApplication
    except Exception:
        return None

    Processing.initialize()
    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

    extent = boundary_layer.extent() if boundary_layer else contour_layer.extent()
    pixel_size = float(cfg.get("dem_pixel_size") or 1.0)
    out_path = Path(cfg.get("dem_tif") or (cfg["output_dir"] / "site_dem.tif"))
    if out_path.exists() and not force:
        try:
            return load_data_layer(cfg["project_dir"], str(out_path))
        except Exception:
            return None
    out_path.parent.mkdir(parents=True, exist_ok=True)

    params = {
        "INTERPOLATION_DATA": [
            {
                "source": contour_layer,
                "zField": cfg.get("contour_z_field") or "Contour",
                "type": 1,
            }
        ],
        "METHOD": 0,
        "EXTENT": extent,
        "PIXEL_SIZE": pixel_size,
        "OUTPUT": str(out_path),
    }
    try:
        processing.run("qgis:tininterpolation", params)
    except Exception:
        return None
    try:
        return load_data_layer(cfg["project_dir"], str(out_path))
    except Exception:
        return None
