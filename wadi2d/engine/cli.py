"""The command line of design note section 5. The QGIS plugin and a later job runner speak only this.

Everything heavy is imported inside the command that needs it: ``schema``, ``doctor`` and ``hms-import`` never
touch CuPy.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from importlib import metadata, util
from pathlib import Path

EXIT_OK = 0
EXIT_HMS = 2
"""An HMS project that cannot become a job is an invalid job."""
PACKAGES = ("numpy", "numba", "rasterio", "h5py", "shapely", "pydantic", "hecdss", "cupy")
NVIDIA_QUERY = ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]
NVIDIA_TIMEOUT_S = 10


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

    arf = sub.add_parser("arf", help="depth-area study: one run per storm area, design-point table")
    arf.add_argument("job")
    arf.add_argument("--out", required=True)
    arf.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    arf.set_defaults(call=_arf)

    products = sub.add_parser("products", help="pixel depth, hazard and their drawing, for a finished run")
    products.add_argument("run", metavar="RUN_DIR")
    products.add_argument("--backend", choices=("auto", "gpu", "cpu"), default=None)
    products.set_defaults(call=_products)

    hms = sub.add_parser("hms-import", help="job.json from an HMS project")
    hms.add_argument("hms_dir", metavar="HMS_DIR")
    hms.add_argument("--basin", required=True)
    hms.add_argument("--met", required=True)
    hms.add_argument("--control", required=True)
    hms.add_argument("--out", required=True)
    hms.set_defaults(call=_hms_import)
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.call(args)


if __name__ == "__main__":
    sys.exit(main())
