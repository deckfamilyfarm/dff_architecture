import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .ogr2ogr_export import normalize_input_path
from .qgis_map import ensure_qgis, load_data_layer
from .raster_export import load_boundary_layer


def load_env(env_path: Optional[str] = None) -> dict:
    load_dotenv(dotenv_path=env_path)
    return {
        "project_dir": Path(os.environ["QGIS_PROJECT_DIR"]),
        "output_dir": Path(os.environ.get("OUTPUT_DIR", "./output")),
        "qgis_prefix": os.environ.get("QGIS_PREFIX_PATH"),
        "contour_shp": os.environ.get("CONTOUR_SHP_PATH"),
        "boundary_path": os.environ.get("SITE_BOUNDARY_PATH"),
        "boundary_layer": os.environ.get("SITE_BOUNDARY_LAYER"),
        "dem_tif": os.environ.get("OUTPUT_DEM_TIF_PATH"),
        "dem_pixel_size": os.environ.get("DEM_PIXEL_SIZE"),
        "contour_z_field": os.environ.get("CONTOUR_Z_FIELD", "Contour"),
    }


def resolve_path(project_dir: Path, path_str: Optional[str]) -> Optional[Path]:
    if not path_str:
        return None
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = project_dir / candidate
    return candidate


def run_export_dem(
    output_path: Optional[str] = None,
    force: bool = False,
    env_path: Optional[str] = None,
) -> Path:
    cfg = load_env(env_path)
    cfg["output_dir"].mkdir(parents=True, exist_ok=True)
    app = ensure_qgis(cfg["qgis_prefix"])

    contour_path = resolve_path(cfg["project_dir"], cfg.get("contour_shp"))
    if not contour_path:
        raise RuntimeError("CONTOUR_SHP_PATH must be set to generate DEM.")
    contour_path = normalize_input_path(str(contour_path))
    if not contour_path.exists():
        raise FileNotFoundError(f"Contour shapefile not found: {contour_path}")

    contour_layer = load_data_layer(cfg["project_dir"], str(contour_path))
    boundary_layer = load_boundary_layer(cfg, None)

    out_path = Path(output_path or cfg.get("dem_tif") or (cfg["output_dir"] / "site_dem.tif"))
    if out_path.exists() and not force:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import processing
        from processing.core.Processing import Processing
        from qgis.analysis import QgsNativeAlgorithms
        from qgis.core import QgsApplication
    except Exception as exc:
        raise RuntimeError("QGIS processing is not available in this environment.") from exc

    Processing.initialize()
    QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

    extent = boundary_layer.extent() if boundary_layer else contour_layer.extent()
    pixel_size = float(cfg.get("dem_pixel_size") or 1.0)

    z_field = cfg.get("contour_z_field") or "Contour"
    field_idx = contour_layer.fields().indexFromName(z_field)
    if field_idx < 0:
        raise RuntimeError(f"Contour Z field not found: {z_field}")
    interp_data = f"{contour_layer.source()}::~::{field_idx}::~::1::~::0"
    params = {
        "INTERPOLATION_DATA": interp_data,
        "METHOD": 0,
        "EXTENT": extent,
        "PIXEL_SIZE": pixel_size,
        "OUTPUT": str(out_path),
    }
    processing.run("qgis:tininterpolation", params)
    return out_path
