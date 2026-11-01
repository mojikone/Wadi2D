# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A stand-in for the engine: design note section 5 in the standard library, for the plugin's tests.

It emits the fields ``wadi2d/run.py`` and ``wadi2d/engine/monitor.py`` emit, and answers ``schema`` from a frozen
dump of the real schema, so a change of contract shows up in ``test_contract.py``. ``WADI2D_FAKE_MODE`` picks the
behaviour: ok, error (numerical failure at a cell), refuse (exit 2), crash (exit 1 with no events), slow (obeys
stop), deaf (ignores stop). ``WADI2D_FAKE_STEPS`` and ``WADI2D_FAKE_STEP_S`` set the pace.
"""

from __future__ import annotations

import json
import os
import struct
import sys
import time
from pathlib import Path

SCHEMA_FILE = Path(__file__).with_name("schema_sample.json")
FAILED_CELL = {"j": 2, "i": 3, "x": 400070.0, "y": 2699950.0, "wave": 41.0}
ESTIMATE = {"cells": 48, "tiles": 1, "device_gb": 1.25, "step_s": 1.5, "steps": 160, "wall_s": 240.0}
WIDTH, HEIGHT, PIXEL = 8, 6, 20.0
ORIGIN = (400000.0, 2700000.0)
EPSG = 32640
REFUSED = "grid.dx is not a multiple of the DEM pixel"
MAPS = ("max_depth", "max_level", "max_speed", "hazard", "arrival", "max_mean_depth")


def write_tiff(path: Path, value: float) -> None:
    """A float32 GeoTIFF with no library; an existing file of this size is rewritten in place."""
    cells = struct.pack(f"<{WIDTH * HEIGHT}f", *[value] * (WIDTH * HEIGHT))
    scale = struct.pack("<3d", PIXEL, PIXEL, 0.0)
    tie = struct.pack("<6d", 0.0, 0.0, 0.0, *ORIGIN, 0.0)
    keys = struct.pack("<12H", 1, 1, 0, 2, 1024, 0, 1, 1, 3072, 0, 1, EPSG)
    nodata = b"-9999\0"
    entries = 14
    extra = 8 + 2 + entries * 12 + 4
    scale_at, tie_at, keys_at, nodata_at = extra, extra + 24, extra + 72, extra + 96
    data_at = extra + 104
    tags = [
        (256, 4, 1, WIDTH), (257, 4, 1, HEIGHT), (258, 3, 1, 32), (259, 3, 1, 1), (262, 3, 1, 1),
        (273, 4, 1, data_at), (277, 3, 1, 1), (278, 4, 1, HEIGHT), (279, 4, 1, len(cells)), (339, 3, 1, 3),
        (33550, 12, 3, scale_at), (33922, 12, 6, tie_at), (34735, 3, 12, keys_at), (42113, 2, 6, nodata_at),
    ]  # fmt: skip
    head = b"II*\0" + struct.pack("<I", 8) + struct.pack("<H", entries)
    head += b"".join(struct.pack("<HHII", *tag) for tag in tags) + struct.pack("<I", 0)
    blob = head + scale + tie + keys + nodata.ljust(8, b"\0") + cells
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("r+b" if path.exists() else "wb") as stream:
        stream.write(blob)


class Events:
    def __init__(self, path: Path) -> None:
        self.stream = path.open("w", encoding="utf-8")

    def emit(self, ev: str, **fields) -> None:
        self.stream.write(json.dumps({"ev": ev, **fields}) + "\n")
        self.stream.flush()


def run(job_path: Path, out: Path, dry_run: bool) -> int:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    mode = os.environ.get("WADI2D_FAKE_MODE", "ok")
    if mode == "crash":
        print("something broke before the first event", file=sys.stderr)
        return 1
    if mode == "refuse":  # as the real CLI does: a job refused before the run has no progress file
        print(json.dumps({"ev": "error", "code": 2, "message": REFUSED}), file=sys.stderr)
        return 2
    if dry_run:
        print(json.dumps(ESTIMATE, indent=2))
        return 0
    out.mkdir(parents=True, exist_ok=True)
    events = Events(out / "progress.jsonl")
    steps = int(os.environ.get("WADI2D_FAKE_STEPS", "8"))
    pause = float(os.environ.get("WADI2D_FAKE_STEP_S", "0.05"))
    duration = job["run"]["duration_s"]
    write_tiff(out / "live" / "depth.tif", 0.0)
    events.emit("start", backend="cpu", cells=48, tiles=1, dx=job["grid"]["dx"], duration_s=duration, t=0.0)
    for step in range(1, steps + 1):
        time.sleep(pause)
        t = duration * step / steps
        events.emit(
            "step", t=t, dt=1.5, steps=step, active_tiles=1, wet_cells=step * 3, volume=step * 10.0,
            mass_error=1e-6, wall=step * pause,
        )  # fmt: skip
        write_tiff(out / "live" / "depth.tif", float(step))
        if mode == "error" and step == steps // 2:
            events.emit("error", code=5, message="time step below the floor", cell=FAILED_CELL)
            events.emit("done", status="numerical failure", code=5, t=t, steps=step)
            return 5
        if mode != "deaf" and (out / "stop").exists():
            (out / "stop").unlink()
            write_tiff(out / "maps" / "max_depth.tif", float(step))
            events.emit("done", status="stopped", code=6, t=t, steps=step)
            return 6
    while mode == "deaf":
        time.sleep(0.05)
    events.emit("warn", message="point P1 is outside the domain")
    for offset, name in enumerate(MAPS):
        write_tiff(out / "maps" / f"{name}.tif", float(offset + 1))
    events.emit("output", kind="maps", path=str(out / "maps"))
    events.emit("done", status="finished", code=0, t=duration, steps=steps, wet_area_km2=0.0192)
    return 0


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ""
    if command == "schema":
        print(SCHEMA_FILE.read_text(encoding="utf-8"))
        return 0
    if command == "doctor":
        leaked = {name: os.environ.get(name) for name in ("PYTHONHOME", "GDAL_DATA", "PROJ_DATA")}
        print(json.dumps({"engine": "fake", "python": sys.executable, "qgis_env": leaked}))
        return 0
    if command == "hms-import":
        out = Path(argv[argv.index("--out") + 1])
        job = {
            "storm": {"kind": "hypothetical", "depth_mm": 120.0, "duration_min": 1440.0},
            "hydrology": {"hms_basin": "basin.basin", "subbasins": [{"name": "S1", "mode": "lumped"}]},
            "run": {"duration_s": 7200.0},
        }
        out.write_text(json.dumps(job), encoding="utf-8")
        return 0
    if command == "run":
        out = Path(argv[argv.index("--out") + 1])
        return run(Path(argv[1]), out, "--dry-run" in argv)
    print(f"unknown command {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
