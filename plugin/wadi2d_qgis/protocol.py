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
CACHE_DIR = "wadi2d_cache"  # beside the run folders: the tables are the one expensive artefact
RUN_FILE = "plugin_run.json"  # written by the plugin: lets a later QGIS session find and stop the process
STDOUT_FILE = "engine.out"
STDERR_FILE = "engine.err"

POLL_MS = 500
STOP_GRACE_S = 30
QUERY_TIMEOUT_S = 600
STDERR_TAIL_CHARS = 600
RECENT_S = 300  # a progress file touched this recently, with no process known, counts as a live run

DEFAULT_ENGINE = r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe -m wadi2d.engine.cli"
ENGINE_MODULE = ("-m", "wadi2d.engine.cli")

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
    return f"{estimate['cells']:,} cells, {estimate['device_gb']:.2f} GB, about {time_text}"


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
