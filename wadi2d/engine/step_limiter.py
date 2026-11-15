"""The step limiter over a run (W85): a ``limiter`` line of progress at every tick, and a point layer of the cells named.

``outputs.step_limiter`` asks for it; off by default, and nothing here runs then. The reading itself is
``solver.limiter.step_limiter``, the same for both backends. The layer holds one point per cell that set the step at a
tick, with how often, when, and the smallest step it gave: a cell that leads for hours with a hydraulic depth no ground
has is a terrain error to mend, which is how TUFLOW HPC's minimum dt map is read.
"""

from __future__ import annotations

from pathlib import Path

import shapely

from wadi2d.solver.limiter import step_limiter

FILE = "step_limiter.gpkg"
LAYER = "step_limiter"
KEPT = (
    "wave", "celerity", "speed", "jump", "depth", "mean_depth", "plan", "bed", "level", "hydraulic_depth", "face_area",
    "face_depth", "dt_without_tile",
)  # fmt: skip
"""What a point keeps from the tick of its smallest step."""
COLUMNS = {
    "ticks": int,
    "t_first_s": float,
    "t_last_s": float,
    "dt_min_s": float,
    "axis": str,
    "crest": int,
} | {name: float for name in KEPT}


class LimiterLog:
    """Bound to one model; ``tick`` once per progress event."""

    def __init__(self, model, tables, progress) -> None:
        self.model, self.tables, self.progress = model, tables, progress
        self.cells: dict[tuple[int, int, str], dict] = {}
        self.strip_ticks = 0
        """Ticks at which a strip beside the tiles led; it is named in the progress, not located."""

    def tick(self, t: float) -> dict | None:
        info = step_limiter(self.model, self.tables)
        if info is None:
            return None
        self.progress.emit("limiter", t=round(t, 3), **info)
        if info["source"] != "tiles":
            self.strip_ticks += 1
            return info
        key = (info["j"], info["i"], info["axis"])
        held = self.cells.get(key)
        if held is None:
            held = self.cells[key] = {
                "ticks": 0,
                "t_first_s": t,
                "dt_min_s": float("inf"),
                "x": info["x"],
                "y": info["y"],
            }
        held["ticks"] += 1
        held["t_last_s"] = t
        if info["dt_tile"] < held["dt_min_s"]:
            held["dt_min_s"] = info["dt_tile"]
            held["axis"], held["crest"] = info["axis"], int(info["crest"])
            held.update({name: info.get(name) for name in KEPT})
        return info

    def write(self, out: Path, crs: str) -> Path | None:
        """The cells into ``step_limiter.gpkg``; None when no tick named one."""
        from wadi2d.io.geopackage import POINTS, VectorLayer, write_geopackage

        if not self.cells:
            return None
        held = sorted(self.cells.values(), key=lambda c: c["dt_min_s"])
        rows = [
            tuple(None if c.get(name) is None else kind(c[name]) for name, kind in COLUMNS.items())
            for c in held
        ]
        points = [shapely.Point(c["x"], c["y"]) for c in held]
        path = out / FILE
        path.unlink(missing_ok=True)
        return write_geopackage(path, [VectorLayer(LAYER, COLUMNS, rows, points, POINTS)], crs)
