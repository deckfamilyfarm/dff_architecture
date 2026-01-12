import argparse

from .qgis_map import run_render
from .freecad_model import run_build
from .ogr2ogr_export import run_export_contours
from .raster_export import run_export_imagery
from .project_export import run_export_project
from .dem_export import run_export_dem


def parse_args():
    parser = argparse.ArgumentParser(description="QGIS map + FreeCAD model helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    map_cmd = sub.add_parser("render-map", help="Render subject property map to PNG.")
    map_cmd.add_argument("--width", type=int, default=1600)
    map_cmd.add_argument("--height", type=int, default=1200)
    map_cmd.add_argument("--env", type=str, default=None, help="Path to .env file")
    map_cmd.add_argument("--config", type=str, default=None, help="Path to map config YAML")

    model_cmd = sub.add_parser("build-3d", help="Build 3D extrusion from footprint.")
    model_cmd.add_argument("--height", type=float, default=3.0)
    model_cmd.add_argument("--fmt", type=str, default="step", choices=["step", "obj"])
    model_cmd.add_argument("--env", type=str, default=None, help="Path to .env file")

    dxf_cmd = sub.add_parser("export-dxf", help="Export contour shapefile to 3D DXF for Rhino.")
    dxf_cmd.add_argument("--input", type=str, default=None, help="Path to contour shapefile")
    dxf_cmd.add_argument("--output", type=str, default=None, help="Path to output DXF")
    dxf_cmd.add_argument("--z-field", type=str, default="Contour", help="Elevation field name")
    dxf_cmd.add_argument("--nlt", type=str, default="LINESTRING25D", help="OGR geometry type")
    dxf_cmd.add_argument(
        "--output-contour-interval",
        type=float,
        default=None,
        help="Keep contours at this interval (e.g., 1 for 1' spacing)",
    )
    dxf_cmd.add_argument(
        "--merge-fragments",
        action="store_true",
        default=None,
        help="Merge line fragments per contour value (uses GDAL sqlite dialect)",
    )
    dxf_cmd.add_argument("--force", action="store_true", help="Regenerate output even if it exists")
    dxf_cmd.add_argument("--env", type=str, default=None, help="Path to .env file")

    img_cmd = sub.add_parser("export-imagery", help="Export WMS imagery to GeoTIFF clipped to boundary.")
    img_cmd.add_argument("--output", type=str, default=None, help="Path to output GeoTIFF")
    img_cmd.add_argument("--boundary", type=str, default=None, help="Boundary layer path or name")
    img_cmd.add_argument("--width", type=int, default=4096, help="Output width in pixels")
    img_cmd.add_argument("--height", type=int, default=4096, help="Output height in pixels")
    img_cmd.add_argument("--force", action="store_true", help="Regenerate output even if it exists")
    img_cmd.add_argument("--env", type=str, default=None, help="Path to .env file")

    proj_cmd = sub.add_parser("export-qgis-project", help="Write a QGIS project for viewing outputs.")
    proj_cmd.add_argument("--output", type=str, default=None, help="Path to output .qgz/.qgs")
    proj_cmd.add_argument("--force", action="store_true", help="Regenerate output even if it exists")
    proj_cmd.add_argument("--env", type=str, default=None, help="Path to .env file")

    dem_cmd = sub.add_parser("export-dem", help="Generate a DEM GeoTIFF from contours.")
    dem_cmd.add_argument("--output", type=str, default=None, help="Path to output GeoTIFF")
    dem_cmd.add_argument("--force", action="store_true", help="Regenerate output even if it exists")
    dem_cmd.add_argument("--env", type=str, default=None, help="Path to .env file")

    all_cmd = sub.add_parser("export-all", help="Export DXF, imagery, DEM, and QGIS project.")
    all_cmd.add_argument("--width", type=int, default=4096, help="Imagery width in pixels")
    all_cmd.add_argument("--height", type=int, default=4096, help="Imagery height in pixels")
    all_cmd.add_argument("--force", action="store_true", help="Regenerate outputs even if they exist")
    all_cmd.add_argument("--env", type=str, default=None, help="Path to .env file")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "render-map":
        out = run_render(width=args.width, height=args.height, env_path=args.env, config_path=args.config)
        print(f"Map written to {out}")

    if args.command == "build-3d":
        # Replace this footprint with your subject geometry (projected coords recommended).
        sample_footprint = [
            (0.0, 0.0),
            (10.0, 0.0),
            (10.0, 8.0),
            (0.0, 8.0),
        ]
        out = run_build(sample_footprint, height=args.height, fmt=args.fmt, env_path=args.env)
        print(f"Model written to {out}")

    if args.command == "export-dxf":
        out = run_export_contours(
            input_path=args.input,
            output_path=args.output,
            z_field=args.z_field,
            nlt=args.nlt,
            contour_interval=args.output_contour_interval,
            merge_fragments=args.merge_fragments,
            force=args.force,
            env_path=args.env,
        )
        print(f"DXF written to {out}")

    if args.command == "export-imagery":
        out = run_export_imagery(
            output_path=args.output,
            boundary_path=args.boundary,
            width=args.width,
            height=args.height,
            force=args.force,
            env_path=args.env,
        )
        print(f"Imagery written to {out}")

    if args.command == "export-qgis-project":
        out = run_export_project(
            output_path=args.output,
            force=args.force,
            env_path=args.env,
        )
        print(f"QGIS project written to {out}")

    if args.command == "export-dem":
        out = run_export_dem(
            output_path=args.output,
            force=args.force,
            env_path=args.env,
        )
        print(f"DEM written to {out}")

    if args.command == "export-all":
        dxf = run_export_contours(
            force=args.force,
            env_path=args.env,
        )
        imagery = run_export_imagery(
            width=args.width,
            height=args.height,
            force=args.force,
            env_path=args.env,
        )
        dem = run_export_dem(
            force=args.force,
            env_path=args.env,
        )
        project = run_export_project(
            force=args.force,
            env_path=args.env,
        )
        print(f"DXF written to {dxf}")
        print(f"Imagery written to {imagery}")
        print(f"DEM written to {dem}")
        print(f"QGIS project written to {project}")


if __name__ == "__main__":
    main()
