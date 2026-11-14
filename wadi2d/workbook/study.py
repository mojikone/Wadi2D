"""A depth-area study's folder as one return period's source of the dam workbook (W74).

Each element is read as the study reads it (:mod:`wadi2d.arf`, :mod:`wadi2d.arf_network`), at its own drainage area:

- a lumped element the study reran at its own area (``read_as`` of :data:`wadi2d.arf.READ_EXACT`) is rerun the same
  way here, lumped only, with the storm at that area, so its hydrograph is the one whose peak the study tabled;
- a design line, or a lumped element a hand-back feeds, is read from the two storm-area runs that bracket its area and
  blended linear in ln A with the weights the study's maps and lines use (:func:`wadi2d.arf.log_area_weights`); pool
  level, storage and each structure's flow are blended alike. The study's tabled peak is ln Q against ln A between the
  two runs' peaks, so the blend's own peak can sit a little under it; the Read me says which reading each element got;
- an element whose water stays on the grid (the study's ``on_grid``) has no flow of its own and is refused, as the study
  refuses it a row.

An element with no row in the study (no drainage area of its own) needs ``--area NAME=KM2``.

Interface: :func:`is_study`, :func:`study_element`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from wadi2d.products.study_lines import STUDY_FILE, is_study, study_runs
from wadi2d.workbook.model import Hydrograph

__all__ = ["blend", "is_study", "rerun_exact", "study_element"]
SAME_TIME_H = 1e-6


def _saved(folder: Path) -> dict:
    return json.loads((folder / STUDY_FILE).read_text(encoding="utf-8"))


def _mix(low, high, w: float):
    if low is None or high is None:
        return None
    n = min(len(low), len(high))
    return (1.0 - w) * np.asarray(low[:n]) + w * np.asarray(high[:n])


def blend(low: Hydrograph, high: Hydrograph, w: float) -> Hydrograph:
    """``(1 - w) * low + w * high`` in every column both runs wrote; the runs must share their times."""
    n = min(len(low.t_h), len(high.t_h))
    if n < 2 or np.max(np.abs(low.t_h[:n] - high.t_h[:n])) > SAME_TIME_H:
        raise ValueError("the study's two runs wrote their series at different times: they cannot be blended")
    structures = {k: _mix(v, high.structures[k], w) for k, v in low.structures.items() if k in high.structures}
    return Hydrograph(
        low.t_h[:n],
        _mix(low.inflow, high.inflow, w),
        _mix(low.outflow, high.outflow, w),
        _mix(low.pool, high.pool, w),
        _mix(low.storage, high.storage, w),
        structures,
    )


def _dem_crs(cfg) -> str:
    import rasterio

    with rasterio.open(cfg.terrain.dem) as dem:
        return dem.crs.to_wkt() if dem.crs is not None else ""


def rerun_exact(run: Path, name: str, area_km2: float) -> Hydrograph:
    """The element rerun alone, lumped, with the storm at its own area: :func:`wadi2d.arf_network.exact_peaks`'s
    run, with its whole hydrograph and, at a reservoir, its pool, storage and structures (W59's columns)."""
    from wadi2d.config.schema import RunConfig
    from wadi2d.engine.network_series import reservoir_columns
    from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
    from wadi2d.hydrology.model import TimeGrid
    from wadi2d.hydrology.network import LumpedEngine
    from wadi2d.run import lumped_rain_at, lumped_view
    from wadi2d.workbook.sources import from_network_columns

    cfg = RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8"))
    crs = _dem_crs(cfg)
    view = lumped_view(cfg, crs)
    if view is None or name not in view.basin.elements:
        raise ValueError(f"{run}: no lumped element {name!r} to rerun")
    h = view.cfg.hydrology
    grid = TimeGrid(h.time_step_min, math.ceil(view.cfg.run.duration_s / SECONDS_PER_MINUTE / h.time_step_min))
    rain = lumped_rain_at(view, area_km2, crs)
    result = LumpedEngine(view.basin).run(rain, grid, only=view.basin.upstream_of(name))
    inflow, outflow = result.inflow[name], result.outflow[name]
    columns = {"t_s": result.grid.minutes * SECONDS_PER_MINUTE, "inflow_m3s": inflow, "outflow_m3s": outflow}
    columns |= reservoir_columns(view.basin.elements[name], inflow, outflow, grid.dt_minutes)
    return from_network_columns(columns)


def study_element(folder: Path | str, name: str, area_km2: float | None = None) -> tuple[Hydrograph, str, float, str]:
    """(hydrograph, element kind, drainage area km2, how it was read in words) of one element of a study."""
    from wadi2d.arf import READ_EXACT, log_area_weights
    from wadi2d.workbook.sources import run_series

    folder = Path(folder)
    saved = _saved(folder)
    row = {r["design_point"]: r for r in saved.get("table", [])}.get(name)
    if name in saved.get("on_grid", []):
        raise ValueError(
            f"{folder.name}: the water above {name!r} stays on the grid, so the study gives it no flow of its own; "
            "a design line there gives one"
        )
    own = float(row["drainage_area_km2"]) if row is not None else None
    area = own if area_km2 is None else float(area_km2)
    if area is None:
        raise ValueError(f"{folder.name}: {name!r} has no row in the study; give its drainage area, --area {name}=KM2")
    areas, runs = study_runs(folder)
    if row is not None and row["read_as"] == READ_EXACT and own is not None and abs(area - own) <= 1e-9 * own:
        words = f"{name}: rerun lumped at its own drainage area, {area:g} km2, as the study reads it."
        return rerun_exact(runs[0], name, area), "Wadi2D lumped element, rerun at its own area", area, words
    if areas.size == 1:
        low = high = 0
        w = 0.0
    else:
        found_low, found_high, found_w = log_area_weights(areas, area)
        low, high, w = int(found_low), int(found_high), float(found_w)
    first, kind = run_series(runs[low], name)
    if w <= 0.0 or high == low:
        hydrograph, words = first, f"{name}: {area:g} km2, read from the run at {areas[low]:g} km2 alone."
    elif w >= 1.0:
        hydrograph = run_series(runs[high], name)[0]
        words = f"{name}: {area:g} km2, read from the run at {areas[high]:g} km2 alone."
    else:
        hydrograph = blend(first, run_series(runs[high], name)[0], w)
        words = (
            f"{name}: {area:g} km2, read from the runs at {areas[low]:g} km2 (weight {1.0 - w:.3f}) and "
            f"{areas[high]:g} km2 (weight {w:.3f}), every ordinate linear in log area, as the study's lines are."
        )
    if row is not None and hydrograph is not None:
        words += f" The study's tabled peak, ln Q against ln A, is {float(row['design_peak_m3s']):,.1f} m3/s."
    return hydrograph, f"{kind}, depth-area study", area, words
