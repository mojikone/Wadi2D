"""A lumped-only run: the network alone, the HMS way, as a run folder the dock opens (W88).

``run.lumped_only``, or a job whose domain lies wholly under catchments left out of the mesh, runs here: no grid, no
tables, no solver. The run folder holds what a 2D run's holds for its network, and nothing it does not have:

- ``config.resolved.json``, ``progress.jsonl`` with ``start`` and ``done`` events;
- ``results.h5`` with the run's attributes and every element's series under ``series/network`` (no mask, no maps:
  the attribute ``lumped_only`` says so), and ``series/network_<element>.csv``;
- ``network.gpkg`` and ``network_peaks.csv`` (:mod:`wadi2d.engine.network_layers`);
- ``lumped_run.json``: the marker the plugin reads, with the elements' peaks.

Every element of the network is written, as HMS computes it whole. With ``hydrology.arf_by_element`` each element is
read as HMS's depth-area analysis reads it: its sub-network run again with the storm area set to its own drainage
area, and its series of record taken from that run (what W79's ``s03_lumped.py`` did by script).

Refused in words: a rain-on-grid subbasin, a hand-back, a job with no rain, and ``arf_by_element`` beside subbasins
with storm areas of their own.

Interface: :func:`run_lumped`, :data:`MARKER`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.engine.network_layers import element_rows, write_network
from wadi2d.engine.network_series import element_columns, write_element
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.io.results import Results

MARKER = "lumped_run.json"
BACKEND = "lumped"


def _refusals(cfg: RunConfig) -> list[str]:
    h = cfg.hydrology
    found = []
    two_d = [s.name for s in h.subbasins if s.mode == "2d"]
    if two_d:
        found.append(
            f"subbasins {', '.join(two_d[:8])}{' and more' if len(two_d) > 8 else ''} are rain-on-grid, and a "
            "lumped-only run has no grid: make them lumped, or run with a 2D part"
        )
    if h.handbacks:
        found.append("a hand-back takes 2D water into the network, and a lumped-only run has no grid")
    if h.hms_basin is None and h.basin_json is None:
        found.append("a lumped-only run needs a lumped network: hydrology.hms_basin or hydrology.basin_json")
    if cfg.storm.kind == "none":
        found.append("a lumped-only run with no rain computes nothing: give a storm")
    if h.arf_by_element and any(s.storm_area_km2 is not None for s in h.subbasins):
        found.append(
            "hydrology.arf_by_element reads every element at its own area: subbasins with a storm area of their own "
            "say otherwise; choose one"
        )
    return found


def run_lumped(cfg: RunConfig, out: Path, crs: str, progress, summary, left_out=None, why: str = "") -> None:
    """The run; ``summary`` is filled as a 2D run fills it. ``left_out`` and ``why`` say how the run came here when
    it was not asked for (a domain wholly under left-out catchments)."""
    from wadi2d.forcing import arf_table, build_storm
    from wadi2d.hydrology.depth_area import analyse_point, point_storm
    from wadi2d.hydrology.model import TimeGrid
    from wadi2d.hydrology.network import LumpedEngine
    from wadi2d.run import EXIT_DONE, InvalidJob, _lumped_basin, _lumped_rain, arf_tags

    found = _refusals(cfg)
    if found:
        raise InvalidJob("; ".join(found))
    t0 = time.monotonic()
    if why:
        progress.emit("warn", message=why)
    h = cfg.hydrology
    storm = build_storm(cfg)
    basin, hms_basin, _cut = _lumped_basin(cfg, crs)
    steps = int(np.ceil(cfg.run.duration_s / SECONDS_PER_MINUTE / h.time_step_min))
    grid = TimeGrid(h.time_step_min, steps)
    rain = _lumped_rain(cfg, storm, basin, hms_basin, crs)
    engine = LumpedEngine(basin)
    t = grid.minutes * SECONDS_PER_MINUTE
    progress.emit("start", backend=BACKEND, cells=0, tiles=0, dx=0.0, duration_s=cfg.run.duration_s, tables_s=0.0, t=0.0)
    series: dict[str, dict] = {}
    areas: dict[str, tuple[float | None, float | None]] = {}
    if h.arf_by_element:
        table = arf_table(cfg.storm)
        at_point = point_storm(rain)
        for name in basin.topological_order():
            point = analyse_point(engine, at_point, grid, name)
            series[name] = element_columns(basin, point.run, name)
            areas[name] = (point.storm_area_km2, float(table.factor(point.storm_area_km2)))
        progress.emit(
            "warn",
            message=f"rain: each of the {len(series)} elements read at the area-reduction table of its own drainage "
            "area, HMS's depth-area analysis; an element's series holds for it and the elements above it",
        )
    else:
        run = engine.run(rain, grid)
        for name in basin.elements:
            if name in run.outflow:
                series[name] = element_columns(basin, run, name)
    results = Results(out / "results.h5", None, crs, cfg.model_dump_json())
    for name, columns in series.items():
        write_element(results, out, name, t, columns)
    rows = element_rows(basin, series, t, areas)
    names = set(left_out.names) if left_out is not None else set()
    try:
        layers = write_network(out, cfg, basin, rows, crs, names)
    except Exception as error:  # the map of the network must not cost a run
        layers = None
        progress.emit("warn", message=f"the network's map layers could not be written: {error}")
    if layers is not None:
        progress.emit("output", kind="network_layers", path=str(layers))
    summary.loop_s = time.monotonic() - t0
    summary.exit_code, summary.status, summary.backend = EXIT_DONE, "finished", BACKEND
    summary.t_end = cfg.run.duration_s
    summary.peaks = {name: (row["outflow_peak_m3s"], row["outflow_peak_h"] * 3600.0) for name, row in rows.items()}
    tags = arf_tags(cfg)
    results.attributes({"status": summary.status, "t_end_s": summary.t_end, "steps": 0, **tags})
    results.close()
    marker = {
        "kind": "lumped",
        "elements": len(rows),
        "arf_by_element": h.arf_by_element,
        "time_step_min": h.time_step_min,
        "duration_s": cfg.run.duration_s,
        "network_layers": layers is not None,
        "peaks": list(rows.values()),
    }
    (out / MARKER).write_text(json.dumps(marker, indent=1), encoding="utf-8")
    summary.done = dict(
        status=summary.status, code=summary.exit_code, partial=False, t=summary.t_end, duration_s=cfg.run.duration_s,
        steps=0, loop_s=round(summary.loop_s, 2), tables_s=0.0, wet_area_km2=0.0, dt_min=0.0, balance={},
        lumped_only=True, elements=len(rows),
    )  # fmt: skip
