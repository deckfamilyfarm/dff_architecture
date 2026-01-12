import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .qgis_map import ensure_qgis, load_data_layer, load_project


def find_gdalwarp(explicit_path: Optional[str], qgis_prefix: Optional[str]) -> Optional[str]:
    if explicit_path:
        return explicit_path
    which = shutil.which("gdalwarp")
    if which:
        return which
    if not qgis_prefix:
        return None
    prefix = Path(qgis_prefix)
    mac_candidate = prefix / "bin" / "gdalwarp"
    if mac_candidate.exists():
        return str(mac_candidate)
    if prefix.name == "qgis" and prefix.parent.name == "apps":
        root = prefix.parents[1]
        win_candidate = root / "bin" / "gdalwarp.exe"
        if win_candidate.exists():
            return str(win_candidate)
        nix_candidate = root / "bin" / "gdalwarp"
        if nix_candidate.exists():
            return str(nix_candidate)
    return None


def load_env(env_path: Optional[str] = None) -> dict:
    load_dotenv(dotenv_path=env_path)
    return {
        "project_dir": Path(os.environ["QGIS_PROJECT_DIR"]),
        "project_file": os.environ.get("QGIS_PROJECT_FILE", "") or "",
        "subject_layer": os.environ.get("SUBJECT_LAYER_NAME", ""),
        "output_dir": Path(os.environ.get("OUTPUT_DIR", "./output")),
        "qgis_prefix": os.environ.get("QGIS_PREFIX_PATH"),
        "imagery_provider": os.environ.get("IMAGERY_PROVIDER", "wms").lower(),
        "wms_url": os.environ.get("WMS_URL"),
        "wms_layers": os.environ.get("WMS_LAYERS"),
        "wms_format": os.environ.get("WMS_FORMAT", "image/jpeg"),
        "wms_crs": os.environ.get("WMS_CRS"),
        "xyz_url": os.environ.get("XYZ_URL"),
        "xyz_zmin": os.environ.get("XYZ_ZMIN"),
        "xyz_zmax": os.environ.get("XYZ_ZMAX"),
        "xyz_crs": os.environ.get("XYZ_CRS"),
        "imagery_path": os.environ.get("IMAGERY_TIF_PATH"),
        "boundary_path": os.environ.get("SITE_BOUNDARY_PATH"),
        "boundary_layer": os.environ.get("SITE_BOUNDARY_LAYER"),
        "gdalwarp_path": os.environ.get("GDALWARP_PATH"),
    }


def resolve_layer_path(project_dir: Path, path_or_name: str) -> Optional[Path]:
    candidate = Path(path_or_name)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    rel = project_dir / candidate
    if rel.exists():
        return rel
    return None


def load_boundary_layer(cfg: dict, project):
    boundary_path = cfg.get("boundary_path")
    boundary_layer_name = cfg.get("boundary_layer") or cfg.get("subject_layer")
    project_dir = cfg["project_dir"]
    if boundary_path:
        maybe = resolve_layer_path(project_dir, boundary_path)
        if maybe:
            return load_data_layer(project_dir, str(maybe))
        try:
            return load_data_layer(project_dir, boundary_path)
        except Exception:
            return None
    if project and boundary_layer_name:
        found = project.mapLayersByName(boundary_layer_name)
        if found:
            return found[0]
    if boundary_layer_name:
        try:
            return load_data_layer(project_dir, boundary_layer_name)
        except Exception:
            return None
    return None


def render_wms_to_geotiff(
    wms_layer,
    extent,
    dest_crs,
    out_path: Path,
    width: int,
    height: int,
):
    from qgis.core import QgsProject, QgsRasterFileWriter, QgsRasterPipe, QgsRasterProjector

    provider = wms_layer.dataProvider()
    pipe = QgsRasterPipe()
    pipe.set(provider.clone() if hasattr(provider, "clone") else provider)

    if wms_layer.crs().isValid() and wms_layer.crs() != dest_crs:
        projector = QgsRasterProjector()
        projector.setCrs(wms_layer.crs(), dest_crs, QgsProject.instance())
        pipe.insert(2, projector)

    writer = QgsRasterFileWriter(str(out_path))
    writer.setCreateOptions(["COMPRESS=LZW", "TILED=YES"])
    res = writer.writeRaster(pipe, width, height, extent, dest_crs)
    if res != QgsRasterFileWriter.NoError:
        raise RuntimeError(f"Failed to write GeoTIFF (error {res}).")


def clip_with_processing(input_path: Path, mask_layer, out_path: Path) -> bool:
    try:
        import processing
        from processing.core.Processing import Processing
        from qgis.analysis import QgsNativeAlgorithms
        from qgis.core import QgsApplication

        Processing.initialize()
        QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
        processing.run(
            "gdal:cliprasterbymasklayer",
            {
                "INPUT": str(input_path),
                "MASK": mask_layer,
                "SOURCE_CRS": None,
                "TARGET_CRS": None,
                "NODATA": None,
                "ALPHA_BAND": False,
                "CROP_TO_CUTLINE": True,
                "KEEP_RESOLUTION": True,
                "OPTIONS": "",
                "DATA_TYPE": 0,
                "OUTPUT": str(out_path),
            },
        )
        return True
    except Exception:
        return False


def clip_with_gdalwarp(
    input_path: Path,
    mask_layer,
    out_path: Path,
    gdalwarp_path: Optional[str],
    qgis_prefix: Optional[str],
) -> bool:
    gdalwarp = find_gdalwarp(gdalwarp_path, qgis_prefix)
    if not gdalwarp:
        return False
    mask_source = getattr(mask_layer, "source", lambda: "")()
    if not mask_source:
        return False
    cmd = [
        gdalwarp,
        "-cutline",
        mask_source,
        "-crop_to_cutline",
        "-of",
        "GTiff",
        str(input_path),
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return True


def run_export_imagery(
    output_path: Optional[str] = None,
    boundary_path: Optional[str] = None,
    width: int = 4096,
    height: int = 4096,
    force: bool = False,
    env_path: Optional[str] = None,
) -> Path:
    cfg = load_env(env_path)
    cfg["output_dir"].mkdir(parents=True, exist_ok=True)

    if cfg["imagery_provider"] == "wms":
        if not cfg.get("wms_url") or not cfg.get("wms_layers"):
            raise RuntimeError("WMS_URL and WMS_LAYERS must be set in .env for WMS imagery.")
    elif cfg["imagery_provider"] == "xyz":
        if not cfg.get("xyz_url"):
            raise RuntimeError("XYZ_URL must be set in .env for XYZ imagery.")
    else:
        raise RuntimeError(f"Unsupported IMAGERY_PROVIDER: {cfg['imagery_provider']}")

    app = ensure_qgis(cfg["qgis_prefix"])

    project = None
    if cfg["project_file"]:
        project = load_project(cfg["project_dir"], cfg["project_file"])

    if cfg["imagery_provider"] == "wms":
        imagery_cfg = {
            "type": "wms",
            "url": cfg["wms_url"],
            "layers": cfg["wms_layers"],
            "format": cfg["wms_format"],
            "crs": cfg["wms_crs"],
            "name": "imagery",
        }
    else:
        zmin = int(cfg["xyz_zmin"]) if cfg.get("xyz_zmin") else None
        zmax = int(cfg["xyz_zmax"]) if cfg.get("xyz_zmax") else None
        imagery_cfg = {
            "type": "xyz",
            "url": cfg["xyz_url"],
            "zmin": zmin,
            "zmax": zmax,
            "crs": cfg["xyz_crs"] or "EPSG:3857",
            "name": "imagery",
        }
    wms_layer = load_data_layer(cfg["project_dir"], imagery_cfg)

    if boundary_path:
        cfg["boundary_path"] = boundary_path
    boundary_layer = load_boundary_layer(cfg, project)
    if not boundary_layer:
        raise RuntimeError("Boundary layer not found. Set SITE_BOUNDARY_PATH or SITE_BOUNDARY_LAYER.")

    from qgis.core import QgsProject as _QgsProject

    _QgsProject.instance().addMapLayer(wms_layer)
    _QgsProject.instance().addMapLayer(boundary_layer)

    dest_crs = boundary_layer.crs()
    extent = boundary_layer.extent()

    out_path = Path(output_path or cfg.get("imagery_path") or (cfg["output_dir"] / "site_imagery.tif"))
    if out_path.exists() and not force:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tif = Path(tmpdir) / "wms_bbox.tif"
        render_wms_to_geotiff(wms_layer, extent, dest_crs, tmp_tif, width, height)
        clipped = clip_with_processing(tmp_tif, boundary_layer, out_path)
        if not clipped:
            clipped = clip_with_gdalwarp(
                tmp_tif,
                boundary_layer,
                out_path,
                cfg.get("gdalwarp_path"),
                cfg.get("qgis_prefix"),
            )
        if not clipped:
            tmp_tif.replace(out_path)
    return out_path
