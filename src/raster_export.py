import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

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


def find_gdal_translate(explicit_path: Optional[str], qgis_prefix: Optional[str]) -> Optional[str]:
    if explicit_path:
        return explicit_path
    which = shutil.which("gdal_translate")
    if which:
        return which
    if not qgis_prefix:
        return None
    prefix = Path(qgis_prefix)
    mac_candidate = prefix / "bin" / "gdal_translate"
    if mac_candidate.exists():
        return str(mac_candidate)
    if prefix.name == "qgis" and prefix.parent.name == "apps":
        root = prefix.parents[1]
        win_candidate = root / "bin" / "gdal_translate.exe"
        if win_candidate.exists():
            return str(win_candidate)
        nix_candidate = root / "bin" / "gdal_translate"
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
        "imagery_output_crs": os.environ.get("IMAGERY_OUTPUT_CRS"),
        "imagery_path": os.environ.get("IMAGERY_TIF_PATH"),
        "imagery_debug_path": os.environ.get("IMAGERY_DEBUG_TIF_PATH"),
        "boundary_path": os.environ.get("SITE_BOUNDARY_PATH"),
        "boundary_layer": os.environ.get("SITE_BOUNDARY_LAYER"),
        "boundary_crs": os.environ.get("SITE_BOUNDARY_CRS"),
        "gdalwarp_path": os.environ.get("GDALWARP_PATH"),
        "gdal_translate_path": os.environ.get("GDAL_TRANSLATE_PATH"),
        "keep_temp_imagery": os.environ.get("KEEP_TEMP_IMAGERY"),
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
    from qgis.core import QgsCoordinateReferenceSystem

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
            layer = load_data_layer(project_dir, boundary_layer_name)
            if cfg.get("boundary_crs"):
                layer.setCrs(QgsCoordinateReferenceSystem(cfg["boundary_crs"]))
            return layer
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
        try:
            ctx = QgsProject.instance().transformContext()
            projector.setCrs(wms_layer.crs(), dest_crs, ctx)
        except Exception:
            projector.setCrs(wms_layer.crs(), dest_crs)
        pipe.insert(2, projector)

    writer = QgsRasterFileWriter(str(out_path))
    writer.setCreateOptions(["COMPRESS=LZW", "TILED=YES"])
    res = writer.writeRaster(pipe, width, height, extent, dest_crs)
    if res != QgsRasterFileWriter.NoError:
        raise RuntimeError(f"Failed to write GeoTIFF (error {res}).")


def fallback_render_to_geotiff(
    layer,
    extent,
    dest_crs,
    out_path: Path,
    width: int,
    height: int,
    gdal_translate_path: Optional[str],
    qgis_prefix: Optional[str],
):
    from qgis.core import QgsMapSettings, QgsMapRendererParallelJob
    try:
        from PyQt5.QtCore import QSize
        from PyQt5.QtGui import QColor
    except Exception:
        from qgis.PyQt.QtCore import QSize
        from qgis.PyQt.QtGui import QColor

    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setExtent(extent)
    settings.setOutputSize(QSize(width, height))
    settings.setDestinationCrs(dest_crs)
    settings.setBackgroundColor(QColor(0, 0, 0, 0))

    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_png = Path(tmpdir) / "render.png"
        image.save(str(tmp_png), "PNG")

        gdal_translate = find_gdal_translate(gdal_translate_path, qgis_prefix)
        if not gdal_translate:
            raise RuntimeError("gdal_translate not found. Set GDAL_TRANSLATE_PATH or add to PATH.")

        srs = dest_crs.authid() or dest_crs.toWkt()
        cmd = [
            gdal_translate,
            "-of",
            "GTiff",
            "-a_srs",
            srs,
            "-a_ullr",
            str(extent.xMinimum()),
            str(extent.yMaximum()),
            str(extent.xMaximum()),
            str(extent.yMinimum()),
            str(tmp_png),
            str(out_path),
        ]
        subprocess.run(cmd, check=True)


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
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


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
    if cfg.get("boundary_crs"):
        from qgis.core import QgsCoordinateReferenceSystem
        boundary_layer.setCrs(QgsCoordinateReferenceSystem(cfg["boundary_crs"]))
    print(f"Boundary CRS: {boundary_layer.crs().authid() or 'unknown'}")
    print(f"Boundary extent: {boundary_layer.extent()}")

    from qgis.core import QgsProject as _QgsProject

    _QgsProject.instance().addMapLayer(wms_layer)
    _QgsProject.instance().addMapLayer(boundary_layer)

    dest_crs = boundary_layer.crs()
    extent = boundary_layer.extent()
    if cfg.get("imagery_output_crs"):
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform
        dest_crs = QgsCoordinateReferenceSystem(cfg["imagery_output_crs"])
        if dest_crs.isValid() and boundary_layer.crs() != dest_crs:
            transform = QgsCoordinateTransform(boundary_layer.crs(), dest_crs, _QgsProject.instance())
            extent = transform.transformBoundingBox(extent)
    if cfg["imagery_provider"] == "xyz":
        test_xyz_tile(cfg, boundary_layer)
    print(f"Imagery CRS: {dest_crs.authid() or 'unknown'}")
    print(f"Imagery extent: {extent}")

    out_path = Path(output_path or cfg.get("imagery_path") or (cfg["output_dir"] / "site_imagery.tif"))
    if out_path.exists() and not force:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Imagery output target: {out_path}")
    print(f"Imagery output dir exists: {out_path.parent.exists()}, writable: {os.access(out_path.parent, os.W_OK)}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tif = Path(tmpdir) / "wms_bbox.tif"
        try:
            render_wms_to_geotiff(wms_layer, extent, dest_crs, tmp_tif, width, height)
        except Exception:
            fallback_render_to_geotiff(
                wms_layer,
                extent,
                dest_crs,
                tmp_tif,
                width,
                height,
                cfg.get("gdal_translate_path"),
                cfg.get("qgis_prefix"),
            )
        print(f"Temp imagery written: {tmp_tif} (exists={tmp_tif.exists()}, size={tmp_tif.stat().st_size if tmp_tif.exists() else 0})")
        if cfg.get("keep_temp_imagery"):
            debug_path = Path(
                cfg.get("imagery_debug_path") or (cfg["output_dir"] / "site_imagery_debug.tif")
            )
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp_tif, debug_path)
            print(f"Temp imagery copied to: {debug_path}")
        clipped = clip_with_processing(tmp_tif, boundary_layer, out_path)
        if not clipped or not out_path.exists():
            clipped = clip_with_gdalwarp(
                tmp_tif,
                boundary_layer,
                out_path,
                cfg.get("gdalwarp_path"),
                cfg.get("qgis_prefix"),
            )
        if not clipped or not out_path.exists():
            shutil.copy2(tmp_tif, out_path)
    if not out_path.exists():
        raise RuntimeError(f"Imagery export failed to write output: {out_path}")
    log_raster_stats(out_path)
    return out_path


def test_xyz_tile(cfg: dict, boundary_layer) -> None:
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

    url_template = cfg.get("xyz_url")
    if not url_template:
        return
    crs_src = boundary_layer.crs()
    crs_wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(crs_src, crs_wgs84, QgsProject.instance())
    center = boundary_layer.extent().center()
    center_wgs = transform.transform(center)
    lat = center_wgs.y()
    lon = center_wgs.x()
    z = int(cfg.get("xyz_zmax") or 19)

    import math

    n = 2 ** z
    xtile = int((lon + 180.0) / 360.0 * n)
    lat = max(min(lat, 85.05112878), -85.05112878)
    lat_rad = math.radians(lat)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    tile_url = url_template.replace("{z}", str(z)).replace("{x}", str(xtile)).replace("{y}", str(ytile))
    req = Request(tile_url, headers={"User-Agent": "dff-tiles/1.0"})
    try:
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                raise RuntimeError(f"XYZ tile request failed: {resp.status} {tile_url}")
            data = resp.read(256)
            if len(data) < 128:
                raise RuntimeError(f"XYZ tile response too small (len={len(data)}): {tile_url}")
            if not (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8")):
                raise RuntimeError(f"XYZ tile response is not an image: {tile_url}")
    except Exception as exc:
        raise RuntimeError(f"XYZ tile test failed. Check URL/network access: {tile_url}") from exc
    print(f"XYZ tile test OK: {tile_url}")


def log_raster_stats(path: Path) -> None:
    try:
        out = subprocess.check_output(["gdalinfo", "-json", "-mm", str(path)], stderr=subprocess.DEVNULL, text=True)
        info = json.loads(out)
        band = info["bands"][0]
        minv = band.get("minimum")
        maxv = band.get("maximum")
        if minv is not None and maxv is not None:
            print(f"Imagery stats: min={minv} max={maxv}")
        if minv == 0.0 and maxv == 0.0:
            print("Warning: imagery appears blank (min/max both 0).")
    except Exception:
        return None
