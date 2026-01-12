import os
import re
import sys
from urllib.parse import quote
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


def add_qgis_to_path(prefix_path: Optional[str] = None):
    """Add QGIS Python directory to sys.path so imports work."""
    if not prefix_path:
        return
    prefix = Path(prefix_path)
    base = prefix.parent.parent  # e.g., .../OSGeo4W
    python_dir = prefix / "python"
    # QGIS ships PyQt in the OSGeo Python; add that site-packages too.
    py_osgeo = prefix.parent / "Python312" / "Lib" / "site-packages"
    # macOS app bundle layout: .../Contents/Resources/python(+/plugins)
    mac_resources = prefix.parent / "Resources" / "python" if "QGIS.app" in prefix.as_posix() else None
    mac_plugins = mac_resources / "plugins" if mac_resources else None
    for path in (python_dir, python_dir / "site-packages", py_osgeo, mac_resources, mac_plugins):
        if not path:
            continue
        if path.exists() and str(path) not in sys.path:
            sys.path.insert(0, str(path))
    # Ensure PATH includes Qt and QGIS bins so DLLs load.
    qt_bin = prefix.parent / "Qt5" / "bin"
    qgis_bin = prefix / "bin"
    base_bin = base / "bin"
    for path in (qt_bin, qgis_bin, base_bin):
        if path.exists():
            os.environ["PATH"] = f"{path}{os.pathsep}{os.environ['PATH']}"


def check_python_version_matches(prefix_path: Optional[str] = None):
    """Raise a clear error if the running Python doesn't match the bundled QGIS Python."""
    if not prefix_path:
        return
    prefix = Path(prefix_path)
    py_dirs = list((prefix.parent).glob("Python3*"))
    if not py_dirs:
        return
    target = py_dirs[0].name  # e.g., Python312
    m = re.match(r"Python(\d)(\d+)", target)
    if not m:
        return
    expected = (int(m.group(1)), int(m.group(2)))
    if sys.version_info[:2] != expected:
        raise RuntimeError(
            f"QGIS bindings require Python {expected[0]}.{expected[1]} from {py_dirs[0]}/python.exe; "
            f"current Python is {sys.version_info[0]}.{sys.version_info[1]} ({sys.executable})."
        )


def ensure_qgis(prefix_path: Optional[str] = None) -> "QgsApplication":
    """Boot QGIS in a headless mode so we can load projects."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("GDAL_PAM_ENABLED", "NO")
    check_python_version_matches(prefix_path)
    add_qgis_to_path(prefix_path)
    from qgis.core import QgsApplication

    if prefix_path:
        QgsApplication.setPrefixPath(prefix_path, True)
    app = QgsApplication([], False)
    app.initQgis()
    return app


def load_project(project_dir: Path, project_file: str) -> "QgsProject":
    from qgis.core import QgsProject

    project_path = project_dir / project_file
    project = QgsProject.instance()
    if not project.read(str(project_path)):
        raise RuntimeError(f"Failed to load QGIS project: {project_path}")
    return project


def load_data_layer(project_dir: Path, rel_path):
    """Load vector or raster layer from a relative path or WMS config."""
    from qgis.core import QgsVectorLayer, QgsRasterLayer

    # WMS config dict: {"type": "wms", "url": "...", "layers": "name", "format": "image/png"}
    if isinstance(rel_path, dict) and rel_path.get("type") == "wms":
        url = rel_path["url"]
        layers = rel_path["layers"]
        fmt = rel_path.get("format", "image/png")
        crs = rel_path.get("crs")
        # QGIS WMS URI format.
        params = [
            f"url={url}",
            "service=WMS",
            "version=1.3.0",
            f"layers={layers}",
            f"format={fmt}",
            "styles=",
            "crs={}".format(crs) if crs else "",
        ]
        uri = "&".join([p for p in params if p])
        layer = QgsRasterLayer(uri, rel_path.get("name", layers), "wms")
        if not layer.isValid():
            raise RuntimeError(f"Failed to load WMS layer: {url} ({layers})")
        return layer
    # XYZ config dict: {"type": "xyz", "url": "...", "zmin": 0, "zmax": 18, "crs": "EPSG:3857"}
    if isinstance(rel_path, dict) and rel_path.get("type") == "xyz":
        from qgis.core import QgsCoordinateReferenceSystem
        url = quote(rel_path["url"], safe=":/?={}@%")
        zmin = rel_path.get("zmin")
        zmax = rel_path.get("zmax")
        crs = rel_path.get("crs")
        params = [
            "type=xyz",
            f"url={url}",
            f"zmin={zmin}" if zmin is not None else "",
            f"zmax={zmax}" if zmax is not None else "",
            f"crs={crs}" if crs else "",
        ]
        uri = "&".join([p for p in params if p])
        layer = QgsRasterLayer(uri, rel_path.get("name", "XYZ Tiles"), "wms")
        if not layer.isValid():
            raise RuntimeError(f"Failed to load XYZ layer: {url}")
        if crs:
            layer.setCrs(QgsCoordinateReferenceSystem(crs))
        return layer

    candidate = project_dir / rel_path
    layer_path = None
    if candidate.exists():
        layer_path = candidate
    else:
        exts = [".gpkg", ".shp", ".geojson", ".tif", ".tiff", ".vrt", ".jp2", ".jpg", ".jpeg", ".png"]
        for ext in exts:
            maybe = project_dir / f"{rel_path}{ext}"
            if maybe.exists():
                layer_path = maybe
                break
    if not layer_path:
        raise FileNotFoundError(
            f"Could not find layer '{rel_path}' in {project_dir} (tried common vector/raster extensions)."
        )

    ext_lower = layer_path.suffix.lower()
    if ext_lower in {".tif", ".tiff", ".vrt", ".jp2", ".jpg", ".jpeg", ".png"}:
        layer = QgsRasterLayer(str(layer_path), layer_path.stem)
    else:
        layer = QgsVectorLayer(str(layer_path), layer_path.stem, "ogr")

    if not layer.isValid():
        raise RuntimeError(f"Failed to load layer: {layer_path}")
    return layer


def load_layer_from_dir(project_dir: Path, layer_name: str):
    """Load a single vector layer directly when no QGIS project file is provided."""
    return load_data_layer(project_dir, layer_name)


def find_subject_layer(project: "QgsProject", layer_name: str):
    layer = project.mapLayersByName(layer_name)
    if not layer:
        raise ValueError(f"Layer not found: {layer_name}")
    return layer[0]


def filter_layer(layer, id_field: str, id_value: str):
    """Apply an attribute filter to isolate the subject property."""
    # QGIS expression quoting is handled by setSubsetString; wrap strings.
    if id_value.isdigit():
        expr = f"\"{id_field}\" = {id_value}"
    else:
        expr = f"\"{id_field}\" = '{id_value}'"
    layer.setSubsetString(expr)
    layer.triggerRepaint()
    return layer


def subject_extent(layer) -> "QgsRectangle":
    from qgis.core import QgsRectangle

    return layer.extent()


def add_north_arrow(layout, page_size):
    from qgis.core import QgsLayoutItemPicture, QgsLayoutPoint, QgsLayoutSize
    from qgis.PyQt.QtCore import QSizeF
    from qgis.core import QgsApplication

    arrow = QgsLayoutItemPicture(layout)
    # Try to find a bundled north arrow SVG.
    svg_paths = QgsApplication.svgPaths() if hasattr(QgsApplication, "svgPaths") else []
    north_svg = None
    for p in svg_paths:
        candidate = Path(p) / "arrows" / "NorthArrow_03.svg"
        if candidate.exists():
            north_svg = str(candidate)
            break
    if north_svg:
        arrow.setPicturePath(north_svg)
    arrow.attemptMove(QgsLayoutPoint(page_size.width() - 30, page_size.height() - 40))
    arrow.attemptResize(QgsLayoutSize(20, 20))
    layout.addLayoutItem(arrow)


def apply_style(layer, style_cfg: Optional[dict], default_outline: bool = False):
    """Apply simple styling to a vector layer."""
    try:
        from qgis.core import QgsWkbTypes, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol, QgsSingleSymbolRenderer
    except Exception:
        return
    if style_cfg is None and not default_outline:
        return

    fill_color = None
    outline_color = None
    outline_width = None
    if style_cfg:
        fill_color = style_cfg.get("fill_color")
        outline_color = style_cfg.get("outline_color")
        outline_width = style_cfg.get("outline_width")
        line_color = style_cfg.get("line_color")
        line_width = style_cfg.get("line_width")
        point_color = style_cfg.get("point_color")
        point_size = style_cfg.get("point_size")
    else:
        # default_outline
        outline_color = "255,0,0"
        outline_width = "0.8"
        fill_color = "255,0,0,0"

    gtype = layer.geometryType()
    if gtype == QgsWkbTypes.PolygonGeometry:
        symbol = QgsFillSymbol.createSimple(
            {
                "color": fill_color or "255,0,0,0",
                "outline_color": outline_color or "255,0,0",
                "outline_width": str(outline_width or "0.8"),
            }
        )
    elif gtype == QgsWkbTypes.LineGeometry:
        symbol = QgsLineSymbol.createSimple(
            {"color": line_color or outline_color or "255,0,0", "width": str(line_width or outline_width or "0.8")}
        )
    elif gtype == QgsWkbTypes.PointGeometry:
        symbol = QgsMarkerSymbol.createSimple(
            {"color": point_color or outline_color or "255,0,0", "size": str(point_size or "2")}
        )
    else:
        return
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def render_map(
    project: "Optional[QgsProject]",
    layers,
    out_path: Path,
    width: int = 1600,
    height: int = 1200,
    title: Optional[str] = None,
    options: Optional[dict] = None,
    extent_layer=None,
):
    """Create a layout with provided layers and export as PNG."""
    from qgis.core import (
        QgsProject,
        QgsLayout,
        QgsLayoutExporter,
        QgsLayoutItemMap,
        QgsLayoutPoint,
        QgsLayoutSize,
        QgsLayoutItemLegend,
        QgsRectangle,
    )
    from qgis.PyQt.QtGui import QColor

    options = options or {}
    layout = QgsLayout(project) if project else QgsLayout(QgsProject.instance())
    layout.initializeDefaults()
    if hasattr(layout, "setName"):
        layout.setName(title or "Subject Map")

    page = layout.pageCollection().pages()[0]
    map_item = QgsLayoutItemMap(layout)
    if hasattr(map_item, "setLayers"):
        # Draw bottom-to-top: first in list is bottom; reverse so overlays stay on top.
        map_item.setLayers(list(reversed(layers)))
    map_item.attemptMove(QgsLayoutPoint(0, 0))
    page_size = page.pageSize()
    map_item.attemptResize(QgsLayoutSize(page_size.width(), page_size.height()))
    target_layer = extent_layer or layers[0]
    if isinstance(target_layer, str):
        # Try to resolve by name.
        matches = [lyr for lyr in layers if getattr(lyr, "name", lambda: "")() == target_layer]
        if matches:
            target_layer = matches[0]
        else:
            target_layer = layers[0]
    map_item.zoomToExtent(target_layer.extent())
    layout.addLayoutItem(map_item)

    if options.get("add_legend", False):
        legend = QgsLayoutItemLegend(layout)
        legend.setLinkedMap(map_item)
        legend.setTitle("Legend")
        legend.attemptMove(QgsLayoutPoint(page_size.width() - 50, 10))
        legend.setBackgroundEnabled(True)
        legend.setBackgroundColor(QColor(255, 255, 255, 230))
        legend.setFrameEnabled(True)
        legend.setBorderColor(QColor(0, 0, 0))
        try:
            from qgis.core import QgsLegendStyle
            title_font = legend.styleFont(QgsLegendStyle.Title)
            title_font.setPointSizeF(8)
            legend.setStyleFont(QgsLegendStyle.Title, title_font)
            sub_font = legend.styleFont(QgsLegendStyle.Subgroup)
            sub_font.setPointSizeF(7)
            legend.setStyleFont(QgsLegendStyle.Subgroup, sub_font)
            item_font = legend.styleFont(QgsLegendStyle.SymbolLabel)
            item_font.setPointSizeF(7)
            legend.setStyleFont(QgsLegendStyle.SymbolLabel, item_font)
        except Exception:
            pass
        layout.addLayoutItem(legend)

    if options.get("add_north_arrow", False):
        add_north_arrow(layout, page_size)

    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = 300
    try:
        from PyQt5.QtCore import QSize
    except Exception:
        from qgis.PyQt.QtCore import QSize
    settings.imageSize = QSize(width, height)
    # Remove existing file to avoid GDAL "update access" errors.
    if out_path.exists():
        out_path.unlink()
    res = exporter.exportToImage(str(out_path), settings)
    if res != QgsLayoutExporter.Success:
        raise RuntimeError(f"Failed to export map: {res}")


def load_env(env_path: Optional[str] = None) -> dict:
    load_dotenv(dotenv_path=env_path)
    env = {
        "project_dir": Path(os.environ["QGIS_PROJECT_DIR"]),
        "project_file": os.environ.get("QGIS_PROJECT_FILE", "") or "",
        "subject_layer": os.environ["SUBJECT_LAYER_NAME"],
        "subject_id_field": os.environ["SUBJECT_ID_FIELD"],
        "subject_id_value": os.environ["SUBJECT_ID_VALUE"],
        "output_dir": Path(os.environ.get("OUTPUT_DIR", "./output")),
        "qgis_prefix": os.environ.get("QGIS_PREFIX_PATH"),
    }
    env["output_dir"].mkdir(parents=True, exist_ok=True)
    return env


def load_map_config(config_path: Optional[str]):
    if not config_path:
        return {}
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Map config not found: {cfg_file}")
    with cfg_file.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("layers", [])
    data.setdefault("options", {})
    data["options"].setdefault("add_legend", False)
    data["options"].setdefault("add_north_arrow", False)
    return data


def run_render(
    width: int = 1600,
    height: int = 1200,
    env_path: Optional[str] = None,
    config_path: Optional[str] = None,
) -> Path:
    cfg = load_env(env_path)
    map_cfg = load_map_config(config_path)
    app = ensure_qgis(cfg["qgis_prefix"])
    layers = []
    project = None

    extent_layer = map_cfg.get("extent_layer")

    if cfg["project_file"]:
        project = load_project(cfg["project_dir"], cfg["project_file"])
        if map_cfg.get("layers"):
            for layer_cfg in map_cfg["layers"]:
                name = layer_cfg.get("name") or layer_cfg["path"]
                found = project.mapLayersByName(name)
                if not found:
                    raise ValueError(f"Layer '{name}' not found in project.")
                layer = found[0]
                layers.append(layer)
                apply_style(layer, layer_cfg.get("style"))
        else:
            layers.append(find_subject_layer(project, cfg["subject_layer"]))
            apply_style(layers[0], map_cfg.get("style"), default_outline=True)
    else:
        if map_cfg.get("layers"):
            for layer_cfg in map_cfg["layers"]:
                layer = load_data_layer(cfg["project_dir"], layer_cfg["path"])
                layers.append(layer)
                apply_style(layer, layer_cfg.get("style"))
        else:
            layers.append(load_layer_from_dir(cfg["project_dir"], cfg["subject_layer"]))
        # Register layers so rendering knows about them.
        from qgis.core import QgsProject as _QgsProject
        for lyr in layers:
            _QgsProject.instance().addMapLayer(lyr)
        # Set project CRS from first layer if not already set.
        if layers and not _QgsProject.instance().crs().isValid():
            _QgsProject.instance().setCrs(layers[0].crs())

    # Default outline on first layer if nothing provided.
    if layers:
        apply_style(layers[0], map_cfg.get("layers", [{}])[0].get("style") if map_cfg.get("layers") else None, default_outline=True)

    # Optional filter applied to first layer only.
    if cfg["subject_id_field"] and cfg["subject_id_value"] and layers:
        filter_layer(layers[0], cfg["subject_id_field"], cfg["subject_id_value"])

    out_file = cfg["output_dir"] / "subject_map.png"
    render_map(
        project,
        layers,
        out_file,
        width=width,
        height=height,
        title=map_cfg.get("title"),
        options=map_cfg.get("options"),
        extent_layer=extent_layer,
    )
    # Intentionally skip app.exitQgis() to avoid crash on some builds; process exit will clean up.
    return out_file
