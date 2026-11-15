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
MIN_TICKS = 10
"""Fewer progress events than this say nothing about who led the run."""
LEAD_SHARE = 0.5
"""A cell that led this share of the events is named in a warning, when its depth is one no ground has."""
DEPTH_RATIO = 3.0
"""The hydraulic depth the rule read, over the water's own depth in the cell, above which the cell looks like a hole."""
STEP_GAIN = 1.5
"""The step without the cell's tile, over the step it gave, under which it is not worth a warning: on the Block 2
window with its hole mended, an edge cell led 27 of 47 events at 0.80 s where the next tile asked for 0.89 s."""


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

    def notes(self) -> list[str]:
        """Plain words when one cell led most of the run with a depth no ground has: the mark of a hole in the DEM."""
        ticks = sum(c["ticks"] for c in self.cells.values()) + self.strip_ticks
        if not self.cells or ticks < MIN_TICKS:
            return []
        c = max(self.cells.values(), key=lambda held: held["ticks"])
        if c["ticks"] < LEAD_SHARE * ticks or c["hydraulic_depth"] < DEPTH_RATIO * max(c["depth"], 1e-6):
            return []
        if c["dt_without_tile"] < STEP_GAIN * c["dt_min_s"]:
            return (
                []
            )  # it led, and the next tile asks for nearly the same step: nothing to gain by mending it
        return [
            f"one cell set the time step at {c['ticks']} of {ticks} progress events: ({c['x']:.0f}, {c['y']:.0f}), water "
            f"{c['depth']:.1f} m deep over {100.0 * c['plan']:.1f} % of the cell beside a face with {c['face_area']:.0f} m2 "
            f"under water, which the step rule reads as {c['hydraulic_depth']:.0f} m of depth: a step of {c['dt_min_s']:.3f} s "
            f"where the next tile would give {c['dt_without_tile']:.3f} s. A hole in the DEM reads like this: look at the "
            "ground there, and if it is not real, fill it with a terrain object"
        ]

    def write(self, out: Path, crs: str) -> Path | None:
        """The cells into ``step_limiter.gpkg``; None when no tick named one."""
        from wadi2d.io.geopackage import POINTS, VectorLayer, add_layer, write_geopackage

        if not self.cells:
            return None
        held = sorted(self.cells.values(), key=lambda c: c["dt_min_s"])
        rows = [
            tuple(None if c.get(name) is None else kind(c[name]) for name, kind in COLUMNS.items())
            for c in held
        ]
        points = [shapely.Point(c["x"], c["y"]) for c in held]
        path = out / FILE
        layer = VectorLayer(LAYER, COLUMNS, rows, points, POINTS)
        if path.is_file():  # in place: QGIS may hold the last run's file open
            return add_layer(path, layer, crs)
        return write_geopackage(path, [layer], crs)
