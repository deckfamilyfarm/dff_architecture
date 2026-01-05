import os
import sys
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


def ensure_freecad(lib_dir: str | None = None):
    """Add FreeCAD library dir to sys.path when running outside the FreeCAD console."""
    if lib_dir and lib_dir not in sys.path:
        sys.path.append(lib_dir)
    import FreeCAD  # noqa: F401
    import Part  # noqa: F401


def polygon_to_wire(coords: Iterable[tuple[float, float]]):
    import FreeCAD
    import Part

    pts = [FreeCAD.Vector(x, y, 0) for x, y in coords]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    wire = Part.makePolygon(pts)
    return wire


def extrude_footprint(coords: Iterable[tuple[float, float]], height: float):
    import Part

    wire = polygon_to_wire(coords)
    face = Part.Face(wire)
    solid = face.extrude(Part.Vector(0, 0, height))
    return solid


def export_solid(solid, out_path: Path, fmt: str = "step"):
    """Export to STEP or OBJ based on fmt."""
    fmt = fmt.lower()
    if fmt == "step":
        solid.exportStep(str(out_path))
    elif fmt == "obj":
        solid.exportObj(str(out_path))
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    return out_path


def load_env(env_path: str | None = None) -> dict:
    load_dotenv(dotenv_path=env_path)
    return {
        "freecad_lib": os.environ.get("FREECAD_LIBRARY_DIR"),
        "output_dir": Path(os.environ.get("OUTPUT_DIR", "./output")),
    }


def run_build(
    coords: Iterable[tuple[float, float]],
    height: float = 3.0,
    fmt: str = "step",
    env_path: str | None = None,
) -> Path:
    cfg = load_env(env_path)
    ensure_freecad(cfg["freecad_lib"])
    cfg["output_dir"].mkdir(parents=True, exist_ok=True)
    solid = extrude_footprint(coords, height)
    out_file = cfg["output_dir"] / f"subject_model.{fmt}"
    export_solid(solid, out_file, fmt=fmt)
    return out_file
