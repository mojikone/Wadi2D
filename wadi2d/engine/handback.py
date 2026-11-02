"""The link from the grid to the live network: lines that tally, a step that reroutes, injections that hold.

At each lumped step the volume that crossed a line in that step, over the step, is the element's inflow for that
period. The network reruns on the inflow so far, and the last ordinate of its outflow enters the grid over the next
period, held. So a period's water leaves the grid in period k and comes back in period k + 1 + lag: one step late by
causality, and no later. A held period keeps each block of water whole, which a line through the ordinates would not:
it would add half a step of delay and round the hydrograph for nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import h5py
import numpy as np

from wadi2d.config.schema import Boundary, Handback, RunConfig
from wadi2d.engine.maxima import Tally
from wadi2d.engine.monitor import Balance, Monitor
from wadi2d.forcing import BoundarySet, Forcing, Injection, open_faces
from wadi2d.hydrology.live_network import LiveNetwork
from wadi2d.hydrology.model import Branching
from wadi2d.io.results import Results, safe_name, write_series_csv
from wadi2d.solver.model import Model
from wadi2d.tables import GridTables

ALIGNED_S = 1e-6
"""A window ending this close to a lumped step ends on it."""
GROUP = "handback"
"""Group of a checkpoint that holds this module's state."""
LINES_KIND, NETWORK_KIND = "handbacks", "network"


def sink_lines(handbacks: list[Handback]) -> list[Boundary]:
    """Each hand-back as the boundary it is inside the grid: a sink, which cannot pass water on to the far side."""
    return [
        Boundary(kind="free", coordinates=h.coordinates, snap_m=h.snap_m, min_share=h.min_share)
        for h in handbacks
    ]


def line_labels(cfg: RunConfig) -> list[str]:
    """What a warning calls each open line, in the order ``boundary_set`` takes them."""
    labels = [f"Open boundary {n}" for n in range(1, len(cfg.boundaries) + 1)]
    return labels + [f"Hand-back {line.name}" for line in cfg.hydrology.handbacks]


@dataclass
class HeldInjection(Injection):
    """An injection whose flow the network sets each lumped step; a window never spans two of them."""

    held: float = 0.0

    def mean_flow(self, t0: float, t1: float) -> float:
        return self.held


class HandBackLink:
    """Everything a run with hand-backs keeps: the series so far is the whole state of the network."""

    def __init__(
        self,
        cfg: RunConfig,
        tables: GridTables,
        model: Model,
        bset: BoundarySet,
        forcing: Forcing,
        network: LiveNetwork,
        monitor: Monitor,
    ) -> None:
        h = cfg.hydrology
        self.handbacks = h.handbacks
        self.network = network
        self.step = network.grid.dt_seconds
        self.tables = tables
        self.ground = tables.zmin[forcing.jj, forcing.ii]
        first = len(bset.opened) - len(h.handbacks)
        self.cells = bset.picked[first:]
        grid = tables.grid
        inner = grid.mask & ~bset.mask
        self.tallies = [self._tally(model, grid, inner, cells) for cells in self.cells]
        monitor.watch(self.tallies)
        monitor.parts.append(self)
        length = network.grid.n_times + 2
        self.flows = {line.name: np.zeros(length) for line in h.handbacks}
        self.last = {line.name: 0.0 for line in h.handbacks}
        self.done = 0
        self.held: dict[str, HeldInjection] = {}
        for n, inj in enumerate(forcing.injections):
            element = network.reentries.get(inj.name)
            if element is not None:
                held = HeldInjection(
                    inj.name, inj.cells, inj.index, inj.lowest, inj.times, inj.flows, inj.min_depth
                )
                forcing.injections[n] = held
                self.held[element] = held
        self.injections = list(self.held.values())
        self.last_run = network.route(self._series(0))
        self._hold(self.last_run)

    @staticmethod
    def _tally(model: Model, grid, inner: np.ndarray, cells: tuple[np.ndarray, np.ndarray]) -> Tally:
        taken = np.zeros(grid.shape, bool)
        taken[cells] = True
        (xf, xs), (yf, ys) = open_faces(grid, inner, taken)
        return Tally(model, xf, xs, yf, ys)

    def notes(self) -> list[str]:
        """What a line or a re-entry may do wrong while the books still close."""
        out = [
            f"Hand-back {line.name} crosses no active face: nothing will enter its reach"
            for line, tally in zip(self.handbacks, self.tallies, strict=True)
            if tally.n == 0
        ]
        lowest = min(float(self.tables.zmin[cells].min()) for cells in self.cells)
        out += [
            f"re-entry {inj.name} stands higher than a hand-back line: if it runs back to the line, the same water "
            "goes round the reach again"
            for inj in self.injections
            if float(self.ground[inj.cells[inj.lowest]]) > lowest
        ]
        return out

    def _series(self, k: int) -> dict[str, np.ndarray]:
        """The inflow of every entered element, ordinates 0 to k."""
        out: dict[str, np.ndarray] = {}
        for line in self.handbacks:
            flow = self.flows[line.name][: k + 1]
            out[line.element] = out[line.element] + flow if line.element in out else flow.copy()
        return out

    def _hold(self, run) -> None:
        for element, inj in self.held.items():
            inj.held = float(run.outflow[element][-1])

    def window_end(self, t: float, t_next: float) -> float:
        """No window crosses a lumped step: the source would mix two periods of a held flow."""
        following = (np.floor(t / self.step + ALIGNED_S) + 1.0) * self.step
        return min(t_next, float(following))

    def reentry_volume(self) -> float:
        """What the held flows put into the window just made."""
        return sum(inj.window for inj in self.injections)

    def exchange(self, t: float) -> None:
        """Take the step that has just ended; called before a window opens, so a stop on the step cannot miss it."""
        k = int(np.floor(t / self.step + ALIGNED_S))
        if k <= self.done:
            return
        for line, tally in zip(self.handbacks, self.tallies, strict=True):
            volume = tally.volume()
            self.flows[line.name][k] = (volume - self.last[line.name]) / self.step
            self.last[line.name] = volume
        self.done = k
        self.last_run = self.network.route(self._series(k))
        self._hold(self.last_run)

    def _partial(self) -> tuple[dict[str, np.ndarray], int]:
        """The series with what crossed since the last step as one more ordinate, and its index."""
        k = self.done + 1
        series = self._series(k)
        for line, tally in zip(self.handbacks, self.tallies, strict=True):
            series[line.element][k] += (tally.volume() - self.last[line.name]) / self.step
        return series, k

    def _end_flows(self, run) -> np.ndarray:
        total = np.zeros(run.grid.n_times)
        for name, second in self.network.routes.ends:
            total = total + (run.branched if second else run.outflow)[name]
        return total

    def finish(self, t: float, balance: Balance) -> None:
        """Book the network into the balance at time t. The grid's own books do not change."""
        self.exchange(t)
        crossed = sum(tally.volume() for tally in self.tallies)
        run = self.last_run
        k = self.done
        ends = self._end_flows(run)
        out = float(ends[:k].sum()) * self.step + float(ends[k]) * (t - k * self.step)
        series, through = self._partial()
        left = balance.reentry + out
        books = self.network.settle(series, crossed, through, left)
        balance.handback = crossed
        balance.network_out = out
        balance.lateral = books.lateral
        balance.network_storage = books.storage
        balance.routing_defect = books.defect
        self.drained = books.drained

    def figures(self, balance: Balance) -> dict[str, float]:
        """The balance's new lines, added to the old ones only in a run that has them."""
        return {
            "handback_m3": balance.handback,
            "reentry_m3": balance.reentry,
            "lateral_m3": balance.lateral,
            "network_out_m3": balance.network_out,
            "network_storage_m3": balance.network_storage,
            "routing_defect_m3": balance.routing_defect,
            "whole_error_m3": balance.whole_error,
            "whole_relative_error": balance.whole_relative,
        }

    def write(self, results: Results, out) -> None:
        """Each line's period flows, each element's flows, in the results file and as CSV."""
        k = self.done
        t = np.arange(k + 1) * self.step
        for line in self.handbacks:
            columns = {"inflow_m3s": self.flows[line.name][: k + 1]}
            results.series(LINES_KIND, line.name, t, columns)
            write_series_csv(out / "series" / f"handback_{safe_name(line.name)}.csv", t, columns)
        run = self.last_run
        for name in self.network.routes.live:
            columns = {"inflow_m3s": run.inflow[name], "outflow_m3s": run.outflow[name]}
            if isinstance(self.network.basin.elements[name], Branching):
                columns["branched_m3s"] = run.branched[name]
            results.series(NETWORK_KIND, name, t, columns)
            write_series_csv(out / "series" / f"network_{safe_name(name)}.csv", t, columns)

    def save(self, f: h5py.File) -> None:
        """The series is the reaches' state: rerouted on load, it gives every reach and pool back."""
        group = f.create_group(GROUP)
        group.attrs["done"] = self.done
        for line, tally in zip(self.handbacks, self.tallies, strict=True):
            item = group.create_group(safe_name(line.name))
            item.attrs["name"] = line.name
            item.attrs["last"] = self.last[line.name]
            item.attrs["volume"] = tally.volume()
            item.create_dataset("flows", data=self.flows[line.name])

    def load(self, f: h5py.File) -> None:
        if GROUP not in f:
            raise ValueError(
                "this checkpoint has no hand-back record, so the water in the reaches would be lost: "
                "run without --resume in a new folder"
            )
        group = f[GROUP]
        self.done = int(group.attrs["done"])
        for line, tally in zip(self.handbacks, self.tallies, strict=True):
            item = group[safe_name(line.name)]
            self.last[line.name] = float(item.attrs["last"])
            tally.restore(float(item.attrs["volume"]))
            self.flows[line.name] = item["flows"][()]
        self.last_run = self.network.route(self._series(self.done))
        self._hold(self.last_run)
