"""The lumped network's hydrographs as results: inflow and outflow of every element, on an HMS or a generated basin.

A part of the monitor with nothing to book and nothing to checkpoint: it writes, at the end, what the base run gave,
as ``series/network/<element>`` in ``results.h5`` and ``series/network_<element>.csv``. Elements the hand-back link runs
live are left to it (:mod:`wadi2d.engine.handback`), which writes their final series under the same names. On an HMS
network only the elements whose water reached the grid are written (``keep``); the rest never ran in this model (W39; his word of 2026-11-07).

Interface: :class:`NetworkSeries`.
"""

from __future__ import annotations

from collections.abc import Iterable

import h5py

from wadi2d.engine.monitor import Balance
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.model import Basin
from wadi2d.hydrology.network import Run
from wadi2d.io.results import Results, safe_name, write_series_csv

NETWORK_KIND = "network"


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

    def write(self, results: Results, out) -> None:
        run = self.run
        t = run.grid.minutes * SECONDS_PER_MINUTE
        for name in self.basin.elements:
            if name in self.live or name not in run.outflow or (self.keep is not None and name not in self.keep):
                continue
            columns = {"inflow_m3s": run.inflow[name], "outflow_m3s": run.outflow[name]}
            if name in run.branched:
                columns["branched_m3s"] = run.branched[name]
            results.series(NETWORK_KIND, name, t, columns)
            write_series_csv(out / "series" / f"network_{safe_name(name)}.csv", t, columns)

    def save(self, f: h5py.File) -> None:
        """Nothing: the base run is rerun from the job on a resume."""

    def load(self, f: h5py.File) -> None:
        """Nothing to restore."""
