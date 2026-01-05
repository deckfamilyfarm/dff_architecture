import argparse

from .qgis_map import run_render
from .freecad_model import run_build


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


if __name__ == "__main__":
    main()
