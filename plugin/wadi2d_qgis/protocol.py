# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine contract as the plugin sees it (design note section 5): one place, no Qt, no QGIS."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

JOB_FILE = "job.json"
PROGRESS_FILE = "progress.jsonl"
STOP_FILE = "stop"
LIVE_DEPTH = "live/depth.tif"
LIVE_LATEST = "live/latest.json"
MAPS_DIR = "maps"
INPUTS_DIR = "inputs"
CONFIG_FILE = "config.resolved.json"
PIXEL_DIR = "pixels"
PIXEL_STATS = "pixels.json"
PIXEL_DEPTH = "pixel_depth.tif"
PIXEL_HAZARD = "pixel_hazard.tif"
PIXEL_SPEED = "pixel_speed.tif"
PIXEL_DV = "pixel_dv.tif"
DEPTH_DRAWING = "depth_drawing.tif"
LAYERS_FILE = "map_layers.gpkg"
HAZARD_LAYER = "hazard_classes"
DOMAIN_LAYER = "domain"
SUBBASIN_LAYER = "subbasins"
INFLOW_LAYER = "inflows"
BOUNDARY_LAYER = "boundaries"
LINE_LAYER = "design_lines"
REACH_LAYER = "reaches"
FRAMES_FILE = "frames.nc"
FRAMES_TIMEOUT_S = 3600  # the full extent takes minutes
FRAMES_EPOCH = (2000, 1, 1)  # the date in the frames file that stands for the start of a run
LINES_LIST = "lines.json"
LINE_REQUEST = "line_request.json"
LINE_RESULT = "line_result.json"
CELL_GRID_FILE = "cell_grid.gpkg"  # in the run folder itself: written at the start of every run
CELL_GRID_LAYER = "cell_grid"
CELL_GRID_SEEN_MM = 1.0  # a cell this big on the screen before its lines are drawn
CACHE_DIR = "wadi2d_cache"  # beside the run folders: the tables are the one expensive artefact
BASIN_DIR = "wadi2d_basin"  # beside the run folders too: basin.json and basin.gpkg, kept so the runs can read them
BASIN_FILE = "basin.json"
BASIN_GEOMETRY = "basin.gpkg"
BASIN_LAYERS = ("subbasins", "reaches", "junctions")
POUR_POINTS_FILE = "pour_points.geojson"
STUDY_SUFFIX = "_arf"  # a study's folder sits beside the run folders, so it shares their grid cache
STUDY_FILE = "study.json"
STUDY_TABLE = "design_points.csv"
COMPOSITE_DIR = "composite"  # in a study's folder, when it was asked for a composite map
RUN_FILE = "plugin_run.json"  # written by the plugin: lets a later QGIS session find and stop the process
STDOUT_FILE = "engine.out"
STDERR_FILE = "engine.err"

POLL_MS = 500
STOP_GRACE_S = 30
QUERY_TIMEOUT_S = 600
STDERR_TAIL_CHARS = 600
RECENT_S = 300  # a progress file touched this recently, with no process known, counts as a live run

ENGINE_MODULE = ("-m", "wadi2d.engine.cli")
ENGINE_FILE = "engine.txt"  # written beside this module by the installers, and in SHARED_ENGINE_FOLDER by the release one
SHARED_ENGINE_FOLDER = "Wadi2D"  # under %LOCALAPPDATA%: a plugin added by QGIS's Install from ZIP has no file beside it
FALLBACK_ENGINE = "python -m wadi2d.engine.cli"


def default_engine(folder: Path | None = None) -> str:
    """The engine the installer found, beside the plugin or in the user's folder, or a plain python on the PATH."""
    places = [(folder or Path(__file__).resolve().parent) / ENGINE_FILE]
    if os.environ.get("LOCALAPPDATA"):
        places.append(Path(os.environ["LOCALAPPDATA"]) / SHARED_ENGINE_FOLDER / ENGINE_FILE)
    for path in places:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return FALLBACK_ENGINE


def cell_grid_scale(finest_m: float) -> int:
    """The scale at which the finest cell reaches ``CELL_GRID_SEEN_MM``; further out the lines would merge into a tint."""
    return round(finest_m * 1000.0 / CELL_GRID_SEEN_MM)


def cell_grid_title(finest_m: float, coarsest_m: float) -> str:
    size = f"{finest_m:g} m" if finest_m == coarsest_m else f"{finest_m:g} to {coarsest_m:g} m"
    return f"Cell grid, {size}, drawn from 1:{cell_grid_scale(finest_m):,} in"


EXIT_FINISHED = 0
EXIT_STOPPED = 6
EXIT_MESSAGES = {
    EXIT_FINISHED: "Finished.",
    1: "The engine failed unexpectedly.",
    2: "The engine refused the job: a setting is invalid.",
    3: "An input file is missing or cannot be read.",
    4: "The requested compute device is not available.",
    5: "The run went numerically unstable.",
    EXIT_STOPPED: "Stopped on request.",
    7: "Out of memory: try a larger cell size or a smaller domain.",
}
ACCESS_VIOLATION = (-1073741819, 3221225477)
"""0xC0000005 as Windows reports it, signed or not: a crash inside a library, on this project the GPU driver (W33)."""
CRASH_MESSAGE = (
    "The engine crashed inside the graphics driver or a library. If another GPU program is running, close it and run "
    "again; if it keeps happening, restart the PC (a driver left damaged by earlier GPU faults does this) or choose "
    "CPU only as the Engine in the Run section."
)
EXIT_MESSAGES.update(dict.fromkeys(ACCESS_VIOLATION, CRASH_MESSAGE))

_QGIS_ENV_PREFIXES = ("PYTHONHOME", "PYTHONPATH", "GDAL_", "PROJ_", "QGIS_", "O4W_", "OSGEO4W", "VSI_")
_QGIS_ENV_NAMES = ("QT_PLUGIN_PATH", "PYQGIS_STARTUP")


def exit_message(code: int | None) -> str:
    """One plain sentence for an exit code; None means the process vanished without one."""
    if code is None:
        return "The engine stopped without reporting why."
    return EXIT_MESSAGES.get(code, f"The engine ended with an unknown code ({code}).")


def parse_engine(text: str) -> list[str]:
    """The engine setting as a program and its arguments.

    Takes a bare executable (spaces allowed), a quoted one, or either followed by arguments. A Python
    interpreter on its own gets the engine module appended.
    """
    text = text.strip()
    if not text:
        raise ValueError("The engine path is empty.")
    if text.startswith('"'):
        parts = [quoted or plain for quoted, plain in re.findall(r'"([^"]*)"|(\S+)', text)]
    else:
        match = re.match(r"^(.+?\.(?:exe|bat|cmd))(?:\s+(.*))?$", text, re.IGNORECASE)
        parts = [match.group(1), *(match.group(2) or "").split()] if match else text.split()
    if len(parts) == 1 and Path(parts[0]).stem.lower().startswith("python"):
        parts.extend(ENGINE_MODULE)
    return parts


def run_args(job: Path | str, out_dir: Path | str, dry_run: bool = False, resume: bool = False) -> list[str]:
    """The arguments of ``wadi2d run``."""
    args = ["run", str(job), "--out", str(out_dir)]
    if dry_run:
        args.append("--dry-run")
    if resume:
        args.append("--resume")
    return args


def study_args(job: Path | str, out_dir: Path | str) -> list[str]:
    """The arguments of ``wadi2d arf``: the engine choice travels in the job."""
    return ["arf", str(job), "--out", str(out_dir)]


def mesh_args(job: Path | str, out_dir: Path | str) -> list[str]:
    """The arguments of ``wadi2d mesh``."""
    return ["mesh", str(job), "--out", str(out_dir)]


def lines_args(run: Path | str, out_file: Path | str, line_file: Path | str | None = None) -> list[str]:
    """The arguments of ``wadi2d lines``: what the run holds, or one line read from its saved frames."""
    args = ["lines", str(run), "--out", str(out_file)]
    return [*args, "--line", str(line_file)] if line_file else args


def parse_mesh(out: str) -> dict | None:
    """The event the preview prints last, or None."""
    for line in reversed(out.strip().splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("ev") == "mesh":
            return event
    return None


def mesh_text(summary: dict) -> str:
    """What the preview says, from its summary file."""
    tiles = ", ".join(f"{n} of {size}" for size, n in summary["tiles_by_size"].items() if n)
    text = f"{summary['cells']:,} cells, {summary['ratio']:g} x fewer than the uniform grid. Tiles: {tiles}."
    lines = [
        f"{line['name']}: {line['near']:g} m for {line['rows']} rows each side, no coarser than {line['far']:g} m "
        f"within {line['reach']:,.0f} m."
        for line in summary.get("lines", [])
    ]
    return " ".join([text, *lines])


def terrain_args(job: Path | str, out_dir: Path | str) -> list[str]:
    """The arguments of ``wadi2d terrain``."""
    return ["terrain", str(job), "--out", str(out_dir)]


def basin_args(job: Path | str, out_dir: Path | str, pour_points: Path | str | None = None) -> list[str]:
    """The arguments of ``wadi2d basin``; the threshold and the lag method travel in the job's ``basin`` part."""
    args = ["basin", str(job), "--out", str(out_dir)]
    if pour_points is not None:
        args += ["--pour-points", str(pour_points)]
    return args


def parse_basin(out: str) -> dict | None:
    """The event ``wadi2d basin`` prints last, or None."""
    for line in reversed(out.strip().splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("ev") == "basin":
            return event
    return None


def clean_env(env: dict[str, str]) -> dict[str, str]:
    """The environment for the engine: QGIS's own Python, GDAL and PROJ must not leak into its interpreter."""
    roots = []
    for name in ("OSGEO4W_ROOT", "QGIS_PREFIX_PATH", "PYTHONHOME"):
        for key, value in env.items():
            if key.upper() == name and value:
                roots.append(_folder_key(value))
    clean = {}
    for key, value in env.items():
        upper = key.upper()
        if upper.startswith(_QGIS_ENV_PREFIXES) or upper in _QGIS_ENV_NAMES:
            continue
        if upper == "PATH":
            kept = [entry for entry in value.split(";") if not _folder_key(entry).startswith(tuple(roots))]
            value = ";".join(kept)
        clean[key] = value
    return clean


def _folder_key(folder: str) -> str:
    return folder.replace("/", "\\").rstrip("\\").lower() + "\\"


def pid_alive(pid: int | None) -> bool:
    """Whether a process exists. A reused pid can fool it; it is only asked about an unfinished run."""
    if not pid or pid < 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except PermissionError:
            return True
        except OSError:
            return False
        return True
    import ctypes
    from ctypes import wintypes

    query_limited, still_active = 0x1000, 259
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(query_limited, False, pid)
    if not handle:
        return False
    code = wintypes.DWORD()
    known = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel.CloseHandle(handle)
    return bool(known) and code.value == still_active


def next_run_dir(folder: Path | str) -> Path:
    """The folder itself, or a numbered sibling when it already holds a run: results are never overwritten."""
    base = Path(folder)
    candidate = base
    number = 1
    while (candidate / PROGRESS_FILE).exists():
        number += 1
        candidate = base.with_name(f"{base.name}_{number}")
    return candidate


def next_study_dir(folder: Path | str) -> Path:
    """Beside the chosen output folder, named after it: a study never lands in a run's folder, nor a run in it."""
    base = Path(folder)
    return next_run_dir(base.with_name(base.name + STUDY_SUFFIX))


def write_run_info(out_dir: Path | str, pid: int, crs: str, t_end: float | None) -> None:
    """What a later session needs and the progress file does not promise."""
    info = {"pid": pid, "crs": crs, "t_end": t_end}
    (Path(out_dir) / RUN_FILE).write_text(json.dumps(info), encoding="utf-8")


def read_run_info(out_dir: Path | str) -> dict:
    try:
        info = json.loads((Path(out_dir) / RUN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return info if isinstance(info, dict) else {}


def parse_estimate(stdout: str) -> dict | None:
    """What ``run --dry-run`` printed."""
    try:
        found = json.loads(stdout)
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def estimate_text(estimate: dict) -> str:
    """Cells, memory and time in one line."""
    seconds = estimate["wall_s"]
    time_text = f"{seconds:.0f} s" if seconds < 90 else f"{seconds / 60:.0f} min"
    if seconds < 1:
        time_text = "1 s"
    if seconds >= 5400:
        time_text = f"{seconds / 3600:.1f} h"
    words = f"{estimate['cells']:,} cells, {estimate['device_gb']:.2f} GB, about {time_text}"
    if estimate.get("maps"):
        words = f"{words}. {estimate['maps']} saved maps, at most {estimate['maps_gb']:.1f} GB of disk"
    return f"{words}. {estimate['note']}" if estimate.get("note") else words


def engine_error_text(stderr: str) -> str:
    """The engine's own sentence from its stderr; the raw tail when it died before it could write one."""
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            report = json.loads(line)
        except ValueError:
            continue
        if isinstance(report, dict) and report.get("message"):
            return str(report["message"])
    return "\n".join(lines)[-STDERR_TAIL_CHARS:]
