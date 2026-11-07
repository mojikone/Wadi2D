"""The lumped elements of a depth-area study, his decision of 2026-11-07.

Each element reads its design flow at its own drainage area, in one of three ways:

- ``exact``: no 2D water above it. It is rerun alone, lumped only, with the storm read at its own drainage area, as
  HMS's depth-area analysis does; seconds, and no interpolation.
- ``runs``: a hand-back carries 2D water into it. It reads the study's 2D runs either side of its drainage area, ln Q
  against ln A, as a design line does; its area also widens the bracketing storm areas.
- ``grid``: water above it runs on the grid and never comes back into the network. Its network series lacks that water,
  so it has no design flow of its own; a design line there gives one.

The 2D runs stay one per storm area, never one per element.

Interface: :class:`ElementPlan`, :func:`plan_elements`, :func:`exact_peaks`, :func:`series_peak`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.model import TimeGrid
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.io.results import safe_name
from wadi2d.run import LumpedView, lumped_rain_at, lumped_view

EXACT, FROM_RUNS, ON_GRID = "exact", "runs", "grid"
MODE_2D = "2d"
SUBBASIN = "subbasin"


@dataclass(frozen=True)
class ElementPlan:
    name: str
    area_km2: float
    how: str


def _two_d(view: LumpedView) -> set[str]:
    return {s.name for s in view.cfg.hydrology.subbasins if s.mode == MODE_2D}


def _full_links(view: LumpedView) -> dict[str, list[str]]:
    """Every element's parents in the whole network, 2D subbasins included: a generated basin's engine leaves them out."""
    if view.generated is None:
        return {name: list(parents) for name, parents in view.basin.upstream.items()}
    elements = view.generated.model["elements"]
    links: dict[str, list[str]] = {e["name"]: [] for e in elements}
    for element in elements:
        below = element.get("downstream")
        if below in links:
            links[below].append(element["name"])
    return links


def _walk(links: dict[str, list[str]], name: str) -> set[str]:
    found, stack = {name}, [name]
    while stack:
        for parent in links.get(stack.pop(), []):
            if parent not in found:
                found.add(parent)
                stack.append(parent)
    return found


def _generated_areas(view: LumpedView) -> dict[str, float]:
    """Each subbasin's area on a generated basin, 2D ones included, km2."""
    if view.generated is None:
        return {}
    from wadi2d.basin.contract import value_of

    return {
        e["name"]: float(value_of(e, "area_km2") or 0.0) for e in view.generated.model["elements"] if e["kind"] == SUBBASIN
    }


def plan_elements(cfg: RunConfig, crs: str) -> tuple[LumpedView | None, list[ElementPlan]]:
    """Every element of the job's lumped network, in network order, and how the study reads it."""
    view = lumped_view(cfg, crs)
    if view is None:
        return None, []
    links = _full_links(view)
    sub_area = _generated_areas(view)
    two_d = _two_d(view)
    into = {below for _above, below in view.cut}
    plans = []
    for name in view.basin.topological_order(None):
        above = _walk(links, name)
        if view.generated is None:  # HMS's own reading: Downstream links only, a diversion's branch left out
            area = view.basin.drainage_area(name)
        else:
            area = sum(sub_area.get(n, 0.0) for n in above)
        if area <= 0.0:
            continue
        if name in view.live:
            how = FROM_RUNS
        elif above & two_d or above & into or above & view.live:
            how = ON_GRID
        else:
            how = EXACT
        plans.append(ElementPlan(name, round(area, 4), how))
    return view, plans


def exact_peaks(view: LumpedView, plans: list[ElementPlan], crs: str) -> dict[str, tuple[float, float]]:
    """(peak m3/s, time s) of each ``exact`` element, its upstream rerun alone with the storm at its own area."""
    h = view.cfg.hydrology
    steps = int(np.ceil(view.cfg.run.duration_s / SECONDS_PER_MINUTE / h.time_step_min))
    grid = TimeGrid(h.time_step_min, steps)
    engine = LumpedEngine(view.basin)
    found: dict[str, tuple[float, float]] = {}
    for plan in plans:
        if plan.how != EXACT:
            continue
        rain = lumped_rain_at(view, plan.area_km2, crs)
        q = engine.run(rain, grid, only=view.basin.upstream_of(plan.name)).outflow[plan.name]
        found[plan.name] = (float(q.max()), float(np.argmax(q)) * grid.dt_seconds)
    return found


def series_peak(run_dir: Path, name: str) -> tuple[float, float]:
    """(peak m3/s, time s) of an element's outflow in one run, from its network series; zeros when it wrote none."""
    path = Path(run_dir) / "series" / f"network_{safe_name(name)}.csv"
    if not path.is_file():
        return 0.0, 0.0
    with path.open(newline="", encoding="utf-8") as f:
        rows = [(float(r["t_s"]), abs(float(r["outflow_m3s"]))) for r in csv.DictReader(f)]
    if not rows:
        return 0.0, 0.0
    t, q = max(rows, key=lambda row: row[1])
    return q, t
