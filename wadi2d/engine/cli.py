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
EXIT_WORKBOOK = 2
"""Inputs the workbook cannot use read as an invalid job, as run.py's EXIT_INVALID."""
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
        left_out_of,
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
            left = left_out_of(cfg, crs)
            if left is not None and left.names:  # the preview shows the mesh the run steps (W88)
                mask = mask & ~left.cells(window.x0, window.y0, cfg.grid.dx, mask.shape)
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
        chosen = cfg.basin.model_dump()  # the job's own settings; a settings file and the flags override them
        if args.settings is not None:
            chosen.update(json.loads(Path(args.settings).read_text(encoding="utf-8")))
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


def _domain(args: argparse.Namespace) -> int:
    """W97: complete the outline with the catchments draining into it, or align it to catchment polygons."""
    import rasterio

    from wadi2d.config.schema import BasinSettings, DomainSettings
    from wadi2d.domain.files import write_domain
    from wadi2d.run import EXIT_DONE, EXIT_INVALID, JobError

    try:
        cfg = _load(args.job)
        basin = cfg.basin.model_dump()
        if args.threshold_km2 is not None:
            basin["stream_threshold_km2"] = args.threshold_km2 or None
        if args.pixel is not None:
            basin["analysis_pixel"] = args.pixel
        chosen = json.loads(Path(args.settings).read_text(encoding="utf-8")) if args.settings else {}
        if args.tolerance_m is not None:
            chosen["align_tolerance_m"] = args.tolerance_m
        settings = DomainSettings.model_validate(chosen)
        crs = ""
        if cfg.terrain.dem is not None:
            with rasterio.open(cfg.terrain.dem) as src:
                crs = src.crs.to_wkt() if src.crs is not None else ""
        source = args.outline or cfg.grid.domain
        if source is None:
            raise ValueError("no outline: give --outline or a job with grid.domain")
        from wadi2d.domain.outline import kept_lines, read_outline

        outline = read_outline(source, crs)
        kept = kept_lines(cfg, args.keep, crs)
        if args.align is None:
            from wadi2d.domain.outline import complete_outline

            done = complete_outline(cfg, outline, kept, BasinSettings.model_validate(basin), settings)
            polygon, report = done.polygon, {"mode": "complete", **done.report}
            changes = [(c.kind, c.geometry, c.km2, c.catchment, c.x, c.y) for c in done.changes]
        else:
            from wadi2d.domain.align import GAP, RIM, align_outline

            if args.align == "job":
                from wadi2d.forcing import load_polygons

                catchments = list(load_polygons(cfg.hydrology, crs).values())
            else:
                from wadi2d.terrain.vector import read_features

                catchments = [s for _p, s in read_features(args.align, crs) if s.geom_type.endswith("Polygon")]
            done = align_outline(outline, catchments, settings, kept, args.cell_m or cfg.grid.dx)
            polygon, report = done.polygon, {"mode": "align", **done.report}
            changes = [(kind, g, g.area / 1e6, 1, g.centroid.x if not g.is_empty else 0.0,
                        g.centroid.y if not g.is_empty else 0.0)
                       for kind, g in ((RIM, done.rim), (GAP, done.gap)) if not g.is_empty]  # fmt: skip
        report["outline"] = str(source)
        written = write_domain(Path(args.out), polygon, Path(str(source)).stem, crs, report, changes)
    except ValueError as error:
        print(json.dumps({"ev": "error", "code": EXIT_INVALID, "message": str(error)}), file=sys.stderr)
        return EXIT_INVALID
    except JobError as error:
        print(json.dumps({"ev": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return error.code
    print(json.dumps({"ev": "domain", **written, "domain_km2": report["domain_km2"], "notes": report["notes"]}))
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


def _drawings(args: argparse.Namespace) -> int:
    from wadi2d.products.runner import draw

    return draw(Path(args.run), args.backend, echo=True)


def _window(args: argparse.Namespace) -> int:
    from wadi2d.products.runner import export_window

    out = Path(args.out) if args.out else None
    return export_window(Path(args.run), tuple(args.box), args.pixel, out, args.backend, echo=True, surface=args.surface)


def _frames(args: argparse.Namespace) -> int:
    from wadi2d.products.time_slider import write_frames

    try:
        path = write_frames(Path(args.run))
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_FRAMES, "message": str(error)}), file=sys.stderr)
        return EXIT_FRAMES
    print(json.dumps({"ev": "done", "path": str(path)}))
    return EXIT_OK


def _protocol_streams():
    """Standard input and output as the two ends of a byte protocol, with everything else that prints sent to stderr.

    A library that writes to standard output, from Python or from C, would otherwise land in the middle of a picture."""
    sink_fd = os.dup(sys.stdout.fileno())
    sys.stdout.flush()
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    if os.name == "nt":
        import msvcrt

        msvcrt.setmode(sink_fd, os.O_BINARY)
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    return sys.stdin.buffer, os.fdopen(sink_fd, "wb")


def _render(args: argparse.Namespace) -> int:
    from wadi2d.render.server import serve

    source, sink = _protocol_streams()
    return serve(Path(args.run), args.backend, source, sink)


def _rain(args: argparse.Namespace) -> int:
    from wadi2d.engine.rain_info import rain_info

    try:
        print(json.dumps(rain_info(args.source, args.variable, args.units, args.interval_min, args.stamp, args.start)))
    except (ValueError, KeyError, OSError, NotImplementedError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_RAIN, "message": str(error)}), file=sys.stderr)
        return EXIT_RAIN
    return EXIT_OK


def _rain_preview(args: argparse.Namespace) -> int:
    """Each lumped subbasin's rain and the 2D area's, after the area reduction, written to ``--out`` (W65)."""
    from wadi2d.engine.rain_preview import rain_preview
    from wadi2d.run import EXIT_INVALID, JobError

    try:
        found = rain_preview(_load(args.job), args.map)
        Path(args.out).write_text(json.dumps(found), encoding="utf-8")
    except JobError as error:
        print(json.dumps({"ev": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return error.code
    except (ValueError, KeyError, OSError, NotImplementedError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_INVALID, "message": str(error)}), file=sys.stderr)
        return EXIT_INVALID
    print(json.dumps({"ev": "done", "path": str(args.out)}))
    return EXIT_OK


def _compare(args: argparse.Namespace) -> int:
    """Observed records beside a finished run's series, with no rerun: the job's own list, or a new file of them."""
    from pydantic import TypeAdapter, ValidationError

    from wadi2d.config.gauges import Observed
    from wadi2d.engine.observed import compare_run

    try:
        observed = None
        if args.observed:
            source = Path(args.observed)
            data = json.loads(source.read_text(encoding="utf-8"))
            items = data.get("observed", []) if isinstance(data, dict) else data
            for item in items:
                if not Path(item["file"]).is_absolute():
                    item["file"] = str((source.parent / item["file"]).resolve())
            observed = TypeAdapter(list[Observed]).validate_python(items)
        report = compare_run(args.run, observed)
    except (ValueError, ValidationError, KeyError, OSError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_FRAMES, "message": str(error)}), file=sys.stderr)
        return EXIT_FRAMES
    print(json.dumps({"ev": "done", "records": len(report["records"]), "failed": report["failed"]}))
    return EXIT_OK if report["records"] or not report["failed"] else EXIT_FRAMES


def _lines(args: argparse.Namespace) -> int:
    from wadi2d.products.result_lines import catalogue, read_line
    from wadi2d.products.study_lines import is_study, read_study_line, study_catalogue

    run = Path(args.run)
    study = is_study(run)  # a depth-area study's folder: lines take their own area from its runs (W53)
    try:
        if args.line:
            request = json.loads(Path(args.line).read_text(encoding="utf-8"))
            reader = read_study_line if study else read_line
            found = reader(run, request["coordinates"], request.get("name", ""))
        else:
            found = study_catalogue(run) if study else catalogue(run)
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


def _breaklines(args: argparse.Namespace) -> int:
    from wadi2d.breaklines import suggest
    from wadi2d.run import EXIT_INVALID, JobError, check_inputs

    try:
        cfg = _load(args.job)
        check_inputs(cfg)
        summary = suggest(cfg, args.out)
    except JobError as error:
        print(json.dumps({"ev": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return error.code
    except (ValueError, RuntimeError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_INVALID, "message": str(error)}), file=sys.stderr)
        return EXIT_INVALID
    print(json.dumps({"ev": "breaklines", **summary}))
    return EXIT_OK


def _hms_import(args: argparse.Namespace) -> int:
    from wadi2d.engine.hms_import import write_job

    try:
        write_job(Path(args.hms_dir), args.basin, args.met, args.control, Path(args.out))
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_HMS, "message": str(error)}), file=sys.stderr)
        return EXIT_HMS
    return EXIT_OK


def _hms_structures(args: argparse.Namespace) -> int:
    """Each reservoir of an HMS basin, its structures and the engine's refusal if any, as JSON (W75)."""
    from wadi2d.engine.hms_structures import reservoir_structures

    try:
        found = reservoir_structures(args.basin, args.project)
        Path(args.out).write_text(json.dumps(found, indent=2), encoding="utf-8")
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_HMS, "message": str(error)}), file=sys.stderr)
        return EXIT_HMS
    print(json.dumps({"ev": "done", "path": str(args.out), "reservoirs": len(found["reservoirs"])}))
    return EXIT_OK


def _pairs(items: list[str] | None, what: str) -> dict[str, str]:
    """``KEY=VALUE`` options as a dict, refused in words when one has no ``=``."""
    found = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep or not key.strip() or not value.strip():
            raise ValueError(f"{what} {item!r}: expected KEY=VALUE")
        found[key.strip()] = value.strip()
    return found


def _muskingum(args: argparse.Namespace) -> int:
    """K, X and subreaches proposed for every reach of a basin, as JSON or as text; nothing is applied (W89)."""
    from wadi2d.config.schema import Hydrology
    from wadi2d.engine.muskingum_proposals import proposal_table, propose_reaches

    try:
        flows = {name: float(value) for name, value in _pairs(args.flow, "--flow").items()}
        step = args.dt
        if step is None and args.control:  # an HMS run steps at its control file's interval (hms-import)
            from wadi2d.hms import load_control

            step = load_control(args.control).time_interval
        if step is None:
            step = Hydrology.model_fields["time_step_min"].default
        if step <= 0.0:
            raise ValueError(f"--dt {step!r}: a step above zero, minutes")
        found = propose_reaches(args.basin, step, flows, args.velocity)
        if args.out:
            Path(args.out).write_text(json.dumps(found, indent=2), encoding="utf-8")
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_HMS, "message": str(error)}), file=sys.stderr)
        return EXIT_HMS
    if args.out:
        print(json.dumps({"ev": "done", "path": str(args.out), "reaches": len(found["reaches"])}))
    else:
        print(proposal_table(found))
    return EXIT_OK


def _workbook(args: argparse.Namespace) -> int:
    from wadi2d.workbook import make
    from wadi2d.workbook.sources import parse_element

    try:
        runs = {k: Path(v) for k, v in _pairs(args.run, "--run").items()}
        dss = {k: Path(v) for k, v in _pairs(args.dss, "--dss").items()}
        areas = {k: float(v) for k, v in _pairs(args.area, "--area").items()}
        path = make(
            args.out,
            [parse_element(e) for e in args.element],
            runs=runs or None,
            dss=dss or None,
            basin_file=Path(args.basin) if args.basin else None,
            areas=areas,
            target=args.target,
            project=args.project,
            method=args.method,
            tile_charts=not args.no_period_charts,
        )
    except (ValueError, KeyError, OSError) as error:
        print(json.dumps({"ev": "error", "code": EXIT_WORKBOOK, "message": str(error)}), file=sys.stderr)
        return EXIT_WORKBOOK
    print(json.dumps({"ev": "workbook", "path": str(path)}))
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

    domain = sub.add_parser(
        "domain", help="the 2D domain completed with the catchments draining into a drawn outline, or aligned to catchments"
    )
    domain.add_argument("job")
    domain.add_argument("--out", required=True)
    domain.add_argument("--outline", help="polygon layer; else the job's grid.domain")
    domain.add_argument("--keep", help="line layer of the edges drawn exactly, beside the job's boundary lines")
    domain.add_argument(
        "--align", metavar="CATCHMENTS", help="align to a polygon layer, or 'job' for the job's subbasin polygons"
    )
    domain.add_argument("--threshold-km2", type=float, help="stream threshold that names a catchment among the changes")
    domain.add_argument("--pixel", type=float, help="analysis pixel, m")
    domain.add_argument("--tolerance-m", type=float, help="alignment tolerance, m")
    domain.add_argument("--cell-m", type=float, help="cells counted outside every catchment, m; else grid.dx")
    domain.add_argument("--settings", help="JSON file of DomainSettings")
    domain.set_defaults(call=_domain)

    arf = sub.add_parser("arf", help="depth-area study: one run per storm area, design-point table")
    arf.add_argument("job")
    arf.add_argument("--out", required=True)
    arf.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    arf.set_defaults(call=_arf)

    products = sub.add_parser("products", help="pixel depth and hazard for a finished run, drawn if its job asks")
    products.add_argument("run", metavar="RUN_DIR")
    products.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    products.set_defaults(call=_products)

    drawings = sub.add_parser(
        "drawings", help="smooth class polygons and the depth drawing, from the pixel rasters a finished run holds"
    )
    drawings.add_argument("run", metavar="RUN_DIR")
    drawings.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    drawings.set_defaults(call=_drawings)

    window = sub.add_parser(
        "window", help="depth, speed and hazard of one window of a finished run at the DEM's pixel or another (W100)"
    )
    window.add_argument("run", metavar="RUN_DIR")
    window.add_argument("box", nargs=4, type=float, metavar=("XMIN", "YMIN", "XMAX", "YMAX"))
    window.add_argument("--pixel", type=float, default=0.0, help="pixel of the rasters, m; 0, the default, the DEM's own")
    window.add_argument("--out", default=None, help="folder of the rasters; by default pixels/windows/ in the run")
    window.add_argument("--surface", choices=("continuous", "corners", "cell_fill"), default=None)
    window.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    window.set_defaults(call=_window)

    frames = sub.add_parser("frames", help="the saved maps of a finished run as one NetCDF file for the time slider")
    frames.add_argument("run", metavar="RUN_DIR")
    frames.set_defaults(call=_frames)

    render = sub.add_parser(
        "render", help="draw a finished run's saved maps on demand at the pixel: requests on stdin, pictures on stdout"
    )
    render.add_argument("run", metavar="RUN_DIR")
    render.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    render.set_defaults(call=_render)

    rain = sub.add_parser("rain", help="what a rain file holds, as JSON")
    rain.add_argument("source")
    rain.add_argument("--variable", default=None)
    rain.add_argument("--units", default="auto")
    rain.add_argument("--interval-min", type=float, default=None)
    rain.add_argument("--stamp", default="end")
    rain.add_argument("--start", default=None)
    rain.set_defaults(call=_rain)

    preview = sub.add_parser(
        "rain-preview", help="each lumped subbasin's rain and the 2D area's after the area reduction, as JSON"
    )
    preview.add_argument("job")
    preview.add_argument("--out", required=True)
    preview.add_argument("--map", default=None, help="also write the storm as a map in this folder (W77)")
    preview.set_defaults(call=_rain_preview)

    lines = sub.add_parser(
        "lines",
        help="a finished run's upfront lines and points, or any line read from its saved maps; given a depth-area "
        "study's folder, the line is read from the two runs either side of its own drainage area",
    )
    lines.add_argument("run", metavar="RUN_DIR")
    lines.add_argument("--line", default=None, help="JSON file with name and coordinates; without it, what the run holds")
    lines.add_argument("--out", required=True)
    lines.set_defaults(call=_lines)

    compare = sub.add_parser("compare", help="observed records beside a finished run's series, and their statistics")
    compare.add_argument("run", metavar="RUN_DIR")
    compare.add_argument(
        "--observed", default=None, help="JSON file with a list of observed records; without it, the job's own"
    )
    compare.set_defaults(call=_compare)

    terrain = sub.add_parser("terrain", help="what the terrain objects do to the ground, without a run")
    terrain.add_argument("job")
    terrain.add_argument("--out", required=True)
    terrain.set_defaults(call=_terrain)

    breaklines = sub.add_parser("breaklines", help="suggested breaklines from the ground, as an editable line layer")
    breaklines.add_argument("job")
    breaklines.add_argument("--out", required=True)
    breaklines.set_defaults(call=_breaklines)

    hms = sub.add_parser("hms-import", help="job.json from an HMS project")
    hms.add_argument("hms_dir", metavar="HMS_DIR")
    hms.add_argument("--basin", required=True)
    hms.add_argument("--met", required=True)
    hms.add_argument("--control", required=True)
    hms.add_argument("--out", required=True)
    hms.set_defaults(call=_hms_import)

    structures = sub.add_parser(
        "hms-structures", help="each reservoir of an HMS basin, its structures and the engine's refusal, as JSON"
    )
    structures.add_argument("basin", metavar="BASIN_FILE")
    structures.add_argument("--project", default=None, help="the .hms file; default the one beside the basin")
    structures.add_argument("--out", required=True)
    structures.set_defaults(call=_hms_structures)

    muskingum = sub.add_parser(
        "muskingum",
        help="Muskingum K, X and subreaches proposed for every reach of an HMS .basin file or a basin.json, from its "
        "section or its length; shown, never applied: the job takes them only from hydrology.muskingum",
    )
    muskingum.add_argument("basin", metavar="BASIN_FILE")
    muskingum.add_argument("--dt", type=float, default=None,
                           help="the lumped step the subreaches are counted for, minutes; default the control file's "
                           "interval, else the job schema's hydrology.time_step_min")
    muskingum.add_argument("--control", default=None, help="an HMS .control file, whose interval is the step")
    muskingum.add_argument("--flow", action="append", help="REACH=M3S, a reference flow, once per reach")
    muskingum.add_argument("--velocity", type=float, default=None,
                           help="a mean velocity for the reaches with no section, m/s")
    muskingum.add_argument("--out", default=None, help="write JSON here; without it the proposals print as text")
    muskingum.set_defaults(call=_muskingum)

    book = sub.add_parser(
        "workbook",
        help="the dam-site Excel workbook: inflow (outflow, pool, storage where a reservoir routes) at named "
        "elements over a set of return periods, from finished runs or HMS DSS files",
    )
    book.add_argument("--out", required=True, help="the .xlsx to write")
    book.add_argument(
        "--element", action="append", required=True, help="NAME or NAME=SHEET, once per dam, in sheet order"
    )
    book.add_argument(
        "--run",
        action="append",
        help="RP=DIR, once per return period (200yr, PMP ...): a finished run, or a depth-area study's folder, whose "
        "elements are then read at their own drainage areas as the study reads them",
    )
    book.add_argument("--dss", action="append", help="RP=FILE.dss of HMS results, once per return period")
    book.add_argument("--basin", default=None, help="HMS .basin file: catchment areas and which elements are reservoirs")
    book.add_argument("--area", action="append", help="NAME=KM2, a catchment area by hand")
    book.add_argument("--target", default="200yr", help="the return period of the side-by-side sheet")
    book.add_argument("--project", default="", help="named in the titles, e.g. 'Block 02'")
    book.add_argument("--method", default="", help="named in the chart titles, e.g. 'depth-area analyses'")
    book.add_argument("--no-period-charts", action="store_true", help="leave out the inflow-outflow chart per period")
    book.set_defaults(call=_workbook)
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
