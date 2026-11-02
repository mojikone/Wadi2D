"""The command line of design note section 5. The QGIS plugin and a later job runner speak only this.

Everything heavy is imported inside the command that needs it: ``schema``, ``doctor`` and ``hms-import`` never
touch CuPy.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import warnings
from importlib import metadata, util
from pathlib import Path

EXIT_OK = 0
EXIT_HMS = 2
EXIT_FRAMES = 3
EXIT_RAIN = 4
"""An HMS project that cannot become a job is an invalid job."""
PACKAGES = ("numpy", "numba", "rasterio", "h5py", "shapely", "pydantic", "hecdss", "cupy")
NVIDIA_QUERY = ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]
NVIDIA_TIMEOUT_S = 10
FOREIGN_ENV = ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA", "GDAL_DRIVER_PATH")
"""Set for a whole user account by another program's GDAL. The engine reads the data in its own packages."""
CUPY_NOISE = "CUDA path could not be detected"
"""CuPy finds its libraries through the pip packages; the warning is about a toolkit the engine does not need."""


def _schema(_args: argparse.Namespace) -> int:
    from wadi2d.config.schema import json_schema

    print(json.dumps(json_schema(), indent=2))
    return EXIT_OK


def _doctor(_args: argparse.Namespace) -> int:
    report: dict[str, object] = {"python": platform.python_version(), "platform": platform.platform()}
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version("cupy-cuda12x" if name == "cupy" else name)
        except metadata.PackageNotFoundError:
            versions[name] = None if util.find_spec(name) is None else "present"
    report["packages"] = versions
    gpus: list[str] = []
    if shutil.which(NVIDIA_QUERY[0]):
        done = subprocess.run(
            NVIDIA_QUERY, capture_output=True, text=True, timeout=NVIDIA_TIMEOUT_S, check=False
        )
        gpus = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    report["gpus"] = gpus
    report["gpu_backend"] = bool(gpus) and versions["cupy"] is not None
    print(json.dumps(report, indent=2))
    return EXIT_OK


def _load(path: str):
    from wadi2d.run import load_job

    return load_job(path)


def _run(args: argparse.Namespace) -> int:
    from wadi2d.run import EXIT_DONE, EXIT_INVALID, JobError, check_inputs, run_job

    try:
        cfg = _load(args.job)
        if args.dry_run:
            from wadi2d.engine.estimate import as_dict, estimate

            check_inputs(cfg)
            print(json.dumps(as_dict(estimate(cfg, args.backend)), indent=2))
            return EXIT_DONE
    except ValueError as error:
        print(json.dumps({"ev": "error", "code": EXIT_INVALID, "message": str(error)}), file=sys.stderr)
        return EXIT_INVALID
    except JobError as error:
        print(json.dumps({"ev": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return error.code
    return run_job(cfg, args.out, args.backend, resume=args.resume, echo=True).exit_code


def _mesh(args: argparse.Namespace) -> int:
    from wadi2d.run import (
        EXIT_DONE,
        EXIT_INVALID,
        JobError,
        check_inputs,
        domain_mask,
        grid_window,
        with_tables,
    )
    from wadi2d.terrain import RasterBed
    from wadi2d.terrain.ground import Ground

    try:
        cfg = with_tables(_load(args.job))
        check_inputs(cfg)
        from wadi2d.mesh.build import build_grid, line_sizes, report, write_preview

        with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
            window = grid_window(cfg, bed)
            mask = domain_mask(cfg, bed, window)
            crs = bed.crs.to_wkt() if bed.crs is not None else ""
            bed.bind(window.x0, window.y0)
            grid = build_grid(cfg, mask, window.x0, window.y0, crs, Ground(bed, window.x0, window.y0))
        summary = report(grid, int(mask.sum()), cfg.grid.dx, line_sizes(cfg))
        written = write_preview(grid, crs, args.out, summary)
    except ValueError as error:
        print(json.dumps({"ev": "error", "code": EXIT_INVALID, "message": str(error)}), file=sys.stderr)
        return EXIT_INVALID
    except JobError as error:
        print(json.dumps({"ev": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return error.code
    print(json.dumps({"ev": "mesh", **written, "cells": summary.cells, "ratio": summary.ratio}))
    return EXIT_DONE


def _basin(args: argparse.Namespace) -> int:
    from wadi2d.basin.build import build_basin
    from wadi2d.config.schema import BasinSettings
    from wadi2d.run import EXIT_DONE, EXIT_INVALID, JobError, check_inputs

    try:
        cfg = _load(args.job)
        check_inputs(cfg)
        chosen = {} if args.settings is None else json.loads(Path(args.settings).read_text(encoding="utf-8"))
        if args.threshold_km2 is not None:
            chosen["stream_threshold_km2"] = args.threshold_km2 or None
        if args.pixel is not None:
            chosen["analysis_pixel"] = args.pixel
        written = build_basin(cfg, BasinSettings.model_validate(chosen), args.pour_points, args.out)
    except ValueError as error:
        print(json.dumps({"ev": "error", "code": EXIT_INVALID, "message": str(error)}), file=sys.stderr)
        return EXIT_INVALID
    except JobError as error:
        print(json.dumps({"ev": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return error.code
    print(json.dumps({"ev": "basin", **written}))
    return EXIT_DONE


def _arf(args: argparse.Namespace) -> int:
    from wadi2d.arf import arf_study
    from wadi2d.run import JobError

    try:
        cfg = _load(args.job)
        return arf_study(cfg, args.out, args.backend, echo=True).exit_code
    except JobError as error:
        print(json.dumps({"ev": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return error.code


def _products(args: argparse.Namespace) -> int:
    from wadi2d.products.runner import remake

    return remake(Path(args.run), args.backend, echo=True)


def _frames(args: argparse.Namespace) -> int:
    from wadi2d.products.time_slider import write_frames

    try:
        path = write_frames(Path(args.run))
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_FRAMES, "message": str(error)}), file=sys.stderr)
        return EXIT_FRAMES
    print(json.dumps({"ev": "done", "path": str(path)}))
    return EXIT_OK


def _rain(args: argparse.Namespace) -> int:
    from wadi2d.engine.rain_info import rain_info

    try:
        print(json.dumps(rain_info(args.source, args.variable, args.units, args.interval_min, args.stamp, args.start)))
    except (ValueError, KeyError, OSError, NotImplementedError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_RAIN, "message": str(error)}), file=sys.stderr)
        return EXIT_RAIN
    return EXIT_OK


def _lines(args: argparse.Namespace) -> int:
    from wadi2d.products.result_lines import catalogue, read_line

    run = Path(args.run)
    try:
        if args.line:
            request = json.loads(Path(args.line).read_text(encoding="utf-8"))
            found = read_line(run, request["coordinates"], request.get("name", ""))
        else:
            found = catalogue(run)
        Path(args.out).write_text(json.dumps(found), encoding="utf-8")
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_FRAMES, "message": str(error)}), file=sys.stderr)
        return EXIT_FRAMES
    print(json.dumps({"ev": "done", "path": str(args.out)}))
    return EXIT_OK


def _terrain(args: argparse.Namespace) -> int:
    from wadi2d.engine.terrain_preview import preview_terrain
    from wadi2d.run import EXIT_INVALID, JobError

    try:
        print(json.dumps(preview_terrain(_load(args.job), args.out), indent=2))
    except JobError as error:
        print(json.dumps({"ev": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return error.code
    except ValueError as error:
        print(json.dumps({"ev": "error", "code": EXIT_INVALID, "message": str(error)}), file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


def _hms_import(args: argparse.Namespace) -> int:
    from wadi2d.engine.hms_import import write_job

    try:
        write_job(Path(args.hms_dir), args.basin, args.met, args.control, Path(args.out))
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_HMS, "message": str(error)}), file=sys.stderr)
        return EXIT_HMS
    return EXIT_OK


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="wadi2d", description="GPU 2D shallow-water engine with hydrology inside"
    )
    sub = top.add_subparsers(dest="command", required=True)
    sub.add_parser("schema", help="JSON Schema of job.json").set_defaults(call=_schema)
    sub.add_parser("doctor", help="environment report").set_defaults(call=_doctor)

    run = sub.add_parser("run", help="one job")
    run.add_argument("job")
    run.add_argument("--out", required=True)
    run.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--resume", action="store_true")
    run.set_defaults(call=_run)

    mesh = sub.add_parser("mesh", help="preview of the mesh: cell-size raster and counts")
    mesh.add_argument("job")
    mesh.add_argument("--out", required=True)
    mesh.set_defaults(call=_mesh)

    basin = sub.add_parser("basin", help="subbasins, reaches and junctions generated from the DEM")
    basin.add_argument("job")
    basin.add_argument("--out", required=True)
    basin.add_argument(
        "--threshold-km2", type=float, help="stream threshold; 0 breaks at the pour points only"
    )
    basin.add_argument("--pour-points", help="point layer; a 'name' field names the junctions")
    basin.add_argument("--pixel", type=float, help="analysis pixel, m")
    basin.add_argument("--settings", help="JSON file of BasinSettings")
    basin.set_defaults(call=_basin)

    arf = sub.add_parser("arf", help="depth-area study: one run per storm area, design-point table")
    arf.add_argument("job")
    arf.add_argument("--out", required=True)
    arf.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    arf.set_defaults(call=_arf)

    products = sub.add_parser("products", help="pixel depth, hazard and their drawing, for a finished run")
    products.add_argument("run", metavar="RUN_DIR")
    products.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    products.set_defaults(call=_products)

    frames = sub.add_parser("frames", help="the saved maps of a finished run as one NetCDF file for the time slider")
    frames.add_argument("run", metavar="RUN_DIR")
    frames.set_defaults(call=_frames)

    rain = sub.add_parser("rain", help="what a rain file holds, as JSON")
    rain.add_argument("source")
    rain.add_argument("--variable", default=None)
    rain.add_argument("--units", default="auto")
    rain.add_argument("--interval-min", type=float, default=None)
    rain.add_argument("--stamp", default="end")
    rain.add_argument("--start", default=None)
    rain.set_defaults(call=_rain)

    lines = sub.add_parser("lines", help="a finished run's upfront lines and points, or any line read from its saved maps")
    lines.add_argument("run", metavar="RUN_DIR")
    lines.add_argument("--line", default=None, help="JSON file with name and coordinates; without it, what the run holds")
    lines.add_argument("--out", required=True)
    lines.set_defaults(call=_lines)

    terrain = sub.add_parser("terrain", help="what the terrain objects do to the ground, without a run")
    terrain.add_argument("job")
    terrain.add_argument("--out", required=True)
    terrain.set_defaults(call=_terrain)

    hms = sub.add_parser("hms-import", help="job.json from an HMS project")
    hms.add_argument("hms_dir", metavar="HMS_DIR")
    hms.add_argument("--basin", required=True)
    hms.add_argument("--met", required=True)
    hms.add_argument("--control", required=True)
    hms.add_argument("--out", required=True)
    hms.set_defaults(call=_hms_import)
    return top


def own_environment() -> None:
    """Before anything heavy is imported: the same cleaning the plugin gives the engine, for a run from a plain shell."""
    for name in FOREIGN_ENV:
        os.environ.pop(name, None)
    warnings.filterwarnings("ignore", message=CUPY_NOISE)


def main(argv: list[str] | None = None) -> int:
    own_environment()
    args = parser().parse_args(argv)
    return args.call(args)


if __name__ == "__main__":
    sys.exit(main())
