"""What a job's storm puts on each lumped subbasin and on the 2D area, before the run (W65).

The dock's Preview rain button asks this, through ``wadi2d rain-preview``. Every number comes from the engine's own
pieces: the storm the run builds (:func:`wadi2d.forcing.build_storm`), the rain the lumped network takes
(``run._lumped_rain``), and the same binding for the 2D area, the domain less the lumped subbasins' polygons. The
hyetographs are on the lumped engine's step, as the network takes them.

The 2D area's depth is an area-weighted mean over the rain pixels; the cells read the pixel under their centre, so on
a coarse rain grid the two can part by a fraction of a per cent at the domain's edge.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import rasterio
import shapely

from wadi2d.config.schema import RunConfig
from wadi2d.forcing import UNIT_DEPTH, build_storm, load_polygons
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.storm.gauges import GaugeStorm
from wadi2d.storm.gridded import GriddedStorm
from wadi2d.terrain.vector import read_features

AREA_2D = "2D area"
"""The name the 2D cells' rain answers to; no subbasin of a job may take it (HMS names never hold a space and a digit
first)."""
M2_PER_KM2 = 1e6
MINUTES_PER_HOUR = 60.0
DECIMALS = 4
AREA_DECIMALS = 6


def _crs(cfg: RunConfig) -> str:
    with rasterio.open(cfg.terrain.dem) as dem:
        return dem.crs.to_wkt() if dem.crs is not None else ""


def _domain(cfg: RunConfig, crs: str) -> shapely.Geometry:
    if cfg.grid.domain is not None:
        return shapely.union_all([shape for _properties, shape in read_features(cfg.grid.domain, crs)])
    if cfg.grid.extent is None:
        raise ValueError("the job has neither grid.domain nor grid.extent: the 2D area is unknown")
    return shapely.box(*cfg.grid.extent)


def _has_network(cfg: RunConfig) -> bool:
    """The condition ``run._network`` routes a lumped network on."""
    h = cfg.hydrology
    lumped = any(s.mode == "lumped" and s.outlet is not None for s in h.subbasins)
    return lumped or any(i.element is not None for i in h.inflows) or bool(h.handbacks) or h.basin_json is not None


def _lumped_names(cfg: RunConfig, basin) -> set[str]:
    """The subbasins whose rain the lumped network takes: on a generated basin every one it holds (its 2D subbasins are
    left out of it); on an HMS basin the lumped subbasins named in the job and every subbasin above an inflow taken from
    an element, less any named 2D."""
    h = cfg.hydrology
    if h.basin_json is not None:
        return set(basin.subbasins)
    named = {s.name: s.mode for s in h.subbasins}
    found = {name for name, mode in named.items() if mode == "lumped"}
    for inflow in h.inflows:
        if inflow.element is not None and inflow.element in basin.elements:
            found |= basin.upstream_of(inflow.element) & set(basin.subbasins)
    return {name for name in found if named.get(name) != "2d"}


def _series(storm, dt_min: float, steps: int) -> dict:
    increments = np.asarray(storm.increments(dt_min, steps), np.float64)
    last = int(np.flatnonzero(increments > 0.0)[-1]) + 1 if np.any(increments > 0.0) else 0
    kept = increments[:last]
    return {
        "depth_mm": round(float(increments.sum()), DECIMALS),
        "peak_mm_h": round(float(kept.max()) * MINUTES_PER_HOUR / dt_min, DECIMALS) if last else 0.0,
        "minutes": [round((n + 1) * dt_min, DECIMALS) for n in range(last)],
        "mm": [round(float(v), DECIMALS) for v in kept],
    }


def _two_d_storm(cfg: RunConfig, area: shapely.Geometry, crs: str):
    """The rain of the 2D area as the lumped network would take it, were the area one subbasin."""
    storm = build_storm(cfg)
    if isinstance(storm, GriddedStorm):
        return storm.bind({AREA_2D: area}, crs).over(AREA_2D)
    if isinstance(storm, GaugeStorm):
        return storm.bind({AREA_2D: area}, crs, crs).over(AREA_2D)
    if cfg.storm.depth_grid is not None:
        from wadi2d.storm.grid_depth import DepthGrid

        depth = DepthGrid.load(cfg.storm.depth_grid, crs or None).mean_over([area])
        return replace(storm, depth_mm=UNIT_DEPTH * depth)
    return storm


def _factor(storm) -> float | None:
    factor = getattr(storm, "area_factor", None)
    if factor is None and getattr(storm, "arf", None) is not None and storm.storm_area_km2 is not None:
        factor = storm.arf.factor(storm.storm_area_km2)
    return None if factor is None else round(float(factor), 6)


def rain_preview(cfg: RunConfig) -> dict:
    """Each lumped subbasin's rain and the 2D area's, after the area reduction, on the lumped engine's step."""
    from wadi2d.run import _lumped_basin, _lumped_rain, _resolved

    crs = _crs(cfg)
    resolved, _generated = _resolved(cfg, crs)
    storm = build_storm(resolved)
    if storm is None:
        raise ValueError("the job has no rain: storm.kind is 'none'")
    h = resolved.hydrology
    dt = h.time_step_min
    steps = math.ceil(resolved.run.duration_s / SECONDS_PER_MINUTE / dt)
    rows = []
    if _has_network(resolved):
        basin, hms_basin, _cut = _lumped_basin(resolved, crs)
        rain = _lumped_rain(resolved, storm, basin, hms_basin, crs)
        for name, subbasin in basin.subbasins.items():
            if name not in _lumped_names(resolved, basin):
                continue
            rows.append({"name": name, "mode": "lumped", "area_km2": round(subbasin.area_km2, AREA_DECIMALS),
                         **_series(rain.over(name), dt, steps)})  # fmt: skip
    masks = [s.name for s in h.subbasins if s.mode == "lumped"]
    polygons = load_polygons(h, crs) if masks else {}
    area = _domain(resolved, crs)
    if masks:
        area = shapely.difference(area, shapely.union_all([polygons[n] for n in masks if n in polygons]))
    if not area.is_empty:
        rows.append({"name": AREA_2D, "mode": "2d", "area_km2": round(area.area / M2_PER_KM2, AREA_DECIMALS),
                     **_series(_two_d_storm(resolved, area, crs), dt, steps)})  # fmt: skip
    return {
        "kind": resolved.storm.kind,
        "step_min": dt,
        "storm_area_km2": resolved.storm.storm_area_km2,
        "area_factor": _factor(storm),
        "areas": rows,
    }
