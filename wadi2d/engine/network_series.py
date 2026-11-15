"""The lumped network's hydrographs as results: inflow and outflow of every element, on an HMS or a generated basin.

A part of the monitor with nothing to book and nothing to checkpoint: it writes, at the end, what the base run gave,
as ``series/network/<element>`` in ``results.h5`` and ``series/network_<element>.csv``. Elements the hand-back link runs
live are left to it (:mod:`wadi2d.engine.handback`), which writes their final series under the same names. On an HMS
network only the elements whose water reached the grid are written (``keep``); the rest never ran in this model (W39; his word of 2026-11-07).

Each element's series carries ``rain_mm`` and ``excess_mm`` per step beside its flows (W64): the chart's rain bar.

Interface: :class:`NetworkSeries`, :func:`element_columns`, :func:`write_element`, :func:`reservoir_columns`,
:func:`rain_columns`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import h5py
import numpy as np

from wadi2d.engine.monitor import Balance
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.model import Basin, Diversion, Element
from wadi2d.hydrology.network import Run, SubbasinWater
from wadi2d.hydrology.reservoir import ReservoirOutflowCurve, ReservoirOutflowStructures
from wadi2d.io.results import Results, safe_name, write_series_csv
from wadi2d.storm.base import FloatArray

NETWORK_KIND = "network"


def reservoir_columns(element: Element, inflow: FloatArray, outflow: FloatArray, dt_minutes: float) -> dict:
    """A reservoir's pool level, m, and storage, m3, beside its flows, and with outflow structures each structure's
    flow and the evaporation; nothing for any other element. Added in W59; the flow columns are unchanged."""
    routing = getattr(element, "routing", None)
    if isinstance(routing, ReservoirOutflowStructures):
        run = routing.run(inflow, dt_minutes)
        columns = {"pool_m": run.pool_m, "storage_m3": run.storage_m3}
        if routing.evaporation is not None:
            columns["evaporation_m3s"] = run.evaporation_m3s
        return columns | run.structures_m3s
    if isinstance(routing, ReservoirOutflowCurve):
        storage, level = routing.pool(inflow, outflow, dt_minutes)
        return {"pool_m": level, "storage_m3": storage}
    return {}


def diversion_columns(element: Element, outflow: FloatArray, branched: FloatArray | None) -> dict:
    """A diversion's passed and diverted flows under their own names (W72), beside ``outflow_m3s`` and
    ``branched_m3s``, which hold the same numbers; nothing for any other element."""
    if not isinstance(element, Diversion) or branched is None:
        return {}
    return {"passed_m3s": outflow, "diverted_m3s": branched}


def rain_columns(basin: Basin, water: Mapping[str, SubbasinWater], name: str, n_times: int) -> dict:
    """``rain_mm`` and ``excess_mm`` in each step ending at the series' times, the first time 0 (W64).

    A subbasin carries its own depths, the area reduction of the storm already in them. Any other element carries the
    area-weighted depths of the subbasins above it through `Downstream` links, the area its drainage area counts. Nothing
    when no subbasin above it was computed with rain.
    """
    above = Basin._walk(basin.main_upstream, name)  # the walk drainage_area takes
    subbasins = basin.subbasins
    parts = [(subbasins[key].area_km2, water[key]) for key in sorted(above) if key in water and key in subbasins]
    area = sum(a for a, _ in parts)
    if not parts or area <= 0.0:
        return {}

    def weighted(depths: list[FloatArray]) -> FloatArray:
        mean = sum(a * d for (a, _), d in zip(parts, depths, strict=True)) / area
        return np.concatenate(([0.0], mean))[:n_times]

    return {
        "rain_mm": weighted([w.precipitation for _, w in parts]),
        "excess_mm": weighted([w.excess for _, w in parts]),
    }


def element_columns(basin: Basin, run: Run, name: str) -> dict:
    """Every column an element's series carries, as :class:`NetworkSeries` writes it."""
    n = run.grid.minutes.size
    columns = {"inflow_m3s": run.inflow[name], "outflow_m3s": run.outflow[name]}
    if name in run.branched:
        columns["branched_m3s"] = run.branched[name]
    columns |= reservoir_columns(basin.elements[name], run.inflow[name], run.outflow[name], run.grid.dt_minutes)
    columns |= diversion_columns(basin.elements[name], run.outflow[name], run.branched.get(name))
    columns |= rain_columns(basin, run.water, name, n)
    return columns


def write_element(results: Results, out, name: str, t: FloatArray, columns: dict) -> None:
    """One element's series into ``results.h5`` and ``series/network_<element>.csv``."""
    results.series(NETWORK_KIND, name, t, columns)
    write_series_csv(out / "series" / f"network_{safe_name(name)}.csv", t, columns)


class NetworkSeries:
    """The base lumped run, written once the 2D run ends."""

    def __init__(self, basin: Basin, run: Run, live: Iterable[str] = (), keep: Iterable[str] | None = None) -> None:
        self.basin = basin
        self.run = run
        self.live = set(live)
        self.keep = None if keep is None else set(keep)
        """The elements to write; None writes every one, as on a generated basin."""

    def notes(self) -> list[str]:
        return []

    def finish(self, t: float, balance: Balance) -> None:
        """Nothing to book: the base run is known before the 2D run starts."""

    def figures(self, balance: Balance) -> dict[str, float]:
        return {}

    def written(self) -> list[str]:
        """The elements :meth:`write` writes, in file order."""
        run = self.run
        return [
            name for name in self.basin.elements
            if name not in self.live and name in run.outflow and (self.keep is None or name in self.keep)
        ]  # fmt: skip

    def write(self, results: Results, out) -> None:
        t = self.run.grid.minutes * SECONDS_PER_MINUTE
        for name in self.written():
            write_element(results, out, name, t, element_columns(self.basin, self.run, name))

    def save(self, f: h5py.File) -> None:
        """Nothing: the base run is rerun from the job on a resume."""

    def load(self, f: h5py.File) -> None:
        """Nothing to restore."""
