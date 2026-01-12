import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def derive_gdal_data(qgis_prefix: Optional[str]) -> Optional[str]:
    if not qgis_prefix:
        return None
    prefix = Path(qgis_prefix)
    if "QGIS.app" in prefix.as_posix():
        candidate = prefix.parent / "Resources" / "gdal"
        return str(candidate) if candidate.exists() else None
    if prefix.name == "qgis" and prefix.parent.name == "apps":
        root = prefix.parents[1]
        candidate = root / "apps" / "gdal" / "share" / "gdal"
        return str(candidate) if candidate.exists() else None
    return None


def find_ogr2ogr(explicit_path: Optional[str], qgis_prefix: Optional[str]) -> Optional[str]:
    if explicit_path:
        return explicit_path
    which = shutil.which("ogr2ogr")
    if which:
        return which
    if not qgis_prefix:
        return None
    prefix = Path(qgis_prefix)
    mac_candidate = prefix / "bin" / "ogr2ogr"
    if mac_candidate.exists():
        return str(mac_candidate)
    if prefix.name == "qgis" and prefix.parent.name == "apps":
        root = prefix.parents[1]
        win_candidate = root / "bin" / "ogr2ogr.exe"
        if win_candidate.exists():
            return str(win_candidate)
        nix_candidate = root / "bin" / "ogr2ogr"
        if nix_candidate.exists():
            return str(nix_candidate)
    return None


def load_env(env_path: Optional[str] = None) -> dict:
    load_dotenv(dotenv_path=env_path)
    contour_interval = os.environ.get("OUTPUT_CONTOUR_INTERVAL")
    merge_fragments = os.environ.get("OUTPUT_MERGE_FRAGMENTS")
    merge_fragments_bool = None
    if merge_fragments is not None:
        merge_fragments_bool = merge_fragments.strip().lower() in {"1", "true", "yes", "y", "on"}
    return {
        "project_dir": Path(os.environ.get("QGIS_PROJECT_DIR", ".")),
        "output_dir": Path(os.environ.get("OUTPUT_DIR", "./output")),
        "qgis_prefix": os.environ.get("QGIS_PREFIX_PATH"),
        "ogr2ogr_path": os.environ.get("OGR2OGR_PATH") or os.environ.get("OG2OGR_PATH"),
        "gdal_data": os.environ.get("GDAL_DATA"),
        "contour_shp": os.environ.get("CONTOUR_SHP_PATH"),
        "contour_dxf": os.environ.get("CONTOUR_DXF_PATH"),
        "contour_z_field": os.environ.get("CONTOUR_Z_FIELD", "Contour"),
        "contour_interval": float(contour_interval) if contour_interval else None,
        "merge_fragments": merge_fragments_bool,
    }


def normalize_input_path(input_path: str) -> Path:
    in_path = Path(input_path)
    if in_path.suffix.lower() == ".shx":
        shp_path = in_path.with_suffix(".shp")
        if shp_path.exists():
            return shp_path
    return in_path


def build_sql(
    layer_name: str,
    z_field: str,
    contour_interval: Optional[float],
    merge_fragments: bool,
) -> Optional[str]:
    if not (contour_interval or merge_fragments):
        return None
    clauses = []
    if contour_interval:
        clauses.append(f"ABS(({z_field} / {contour_interval}) - ROUND({z_field} / {contour_interval})) < 1e-6")
    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    if merge_fragments:
        return (
            f"SELECT ST_LineMerge(ST_Collect(geometry)) AS geometry, {z_field} "
            f"FROM {layer_name}{where_sql} GROUP BY {z_field}"
        )
    return f"SELECT * FROM {layer_name}{where_sql}"


def run_export_contours(
    input_path: Optional[str] = None,
    output_path: Optional[str] = None,
    z_field: str = "Contour",
    nlt: str = "LINESTRING25D",
    contour_interval: Optional[float] = None,
    merge_fragments: Optional[bool] = None,
    force: bool = False,
    env_path: Optional[str] = None,
) -> Path:
    cfg = load_env(env_path)
    in_path_str = input_path or cfg["contour_shp"]
    if not in_path_str:
        raise FileNotFoundError("Contour shapefile not provided. Set --input or CONTOUR_SHP_PATH.")
    in_candidate = Path(in_path_str)
    if not in_candidate.is_absolute():
        in_candidate = cfg["project_dir"] / in_candidate
    in_path = normalize_input_path(str(in_candidate))
    if not in_path.exists():
        raise FileNotFoundError(f"Contour shapefile not found: {in_path}")
    out_path_str = output_path or cfg["contour_dxf"]
    out_path = Path(out_path_str) if out_path_str else cfg["output_dir"] / f"{in_path.stem}_3d.dxf"
    if out_path.exists() and not force:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ogr2ogr_path = find_ogr2ogr(cfg["ogr2ogr_path"], cfg["qgis_prefix"])
    if not ogr2ogr_path:
        raise FileNotFoundError("ogr2ogr not found. Set OGR2OGR_PATH or add it to PATH.")

    gdal_data = cfg["gdal_data"] or derive_gdal_data(cfg["qgis_prefix"])
    env = os.environ.copy()
    if gdal_data:
        env["GDAL_DATA"] = gdal_data

    interval = contour_interval if contour_interval is not None else cfg.get("contour_interval")
    merge = merge_fragments if merge_fragments is not None else bool(cfg.get("merge_fragments"))
    sql = build_sql(in_path.stem, z_field or cfg["contour_z_field"], interval, merge)
    cmd = [
        ogr2ogr_path,
        "-f",
        "DXF",
        str(out_path),
        str(in_path),
        "-zfield",
        z_field or cfg["contour_z_field"],
        "-nlt",
        nlt,
        "-skipfailures",
    ]
    if sql:
        cmd.extend(["-dialect", "sqlite", "-sql", sql])
    subprocess.run(cmd, check=True, env=env)
    return out_path
