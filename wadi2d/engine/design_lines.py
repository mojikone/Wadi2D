"""A design line's flow of record on a generated basin: the grid's discharge plus the lumped water that passes the line
inside the network (W41).

On a generated basin a design line becomes a junction at each stream it crosses. Where that junction's route is a
reach, its water travels inside the lumped reach past the line and enters the grid only at the reach's end, so the grid
line sees only the rain-on-grid around it. W39 measured 0.69 m3/s on the line against 410.2 in the network. The record
adds each such junction's network outflow, signed as the line counts flow (positive to its right). From it comes the 2D
water a hand-back below the line took into the junction, since the grid already counted that water as it crossed. A
junction whose water enters the grid is not added: its entry lies up the wadi, clear above the line
(:mod:`wadi2d.engine.entries`), so the grid carries it across.

The record is ``series/design_<line>.csv`` and ``series/design/<line>`` in ``results.h5``, with the grid's part, the
network's part and their total. The run's peak for that line is the total's.

Interface: :func:`plans`, :func:`records`, :class:`DesignPlan`, :data:`DESIGN_KIND`.
"""

from __future__ import annotations

import csv
import itertools
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wadi2d.basin.routes import ROUTE_REACH
from wadi2d.io.results import safe_name

DESIGN_KIND = "design"
GRID, NETWORK, TOTAL = "grid_m3s", "network_m3s", "total_m3s"


@dataclass(frozen=True)
class Part:
    """A junction on the line whose water passes it inside a reach."""

    element: str
    sign: float
    """+1 when the junction drains to the line's right, the side a line counts positive."""
    handback: str | None
    """A hand-back line below the design line that takes 2D water into this junction: subtracted."""


@dataclass(frozen=True)
class DesignPlan:
    line: str
    parts: tuple[Part, ...]


def _side(coordinates, point) -> float:
    """+1 right of the line's nearest segment, -1 left, 0 on it."""
    line = np.asarray(coordinates, dtype=float)
    p = np.asarray(point, dtype=float)
    best, side = np.inf, 0.0
    for a, b in itertools.pairwise(line):
        d = b - a
        length2 = float(np.dot(d, d))
        if length2 == 0.0:
            continue
        t = np.clip(np.dot(p - a, d) / length2, 0.0, 1.0)
        dist = float(np.linalg.norm(p - (a + t * d)))
        if dist < best:
            best, side = dist, float(-np.sign(d[0] * (p - a)[1] - d[1] * (p - a)[0]))
    return side


def _line_of(element: dict, names: set[str]) -> str | None:
    """The design line a junction was built on: its pour point's own line, or an alias that names one."""
    pour = element.get("pour_point") or {}
    if pour.get("line") in names:
        return pour["line"]
    for alias in pour.get("aliases", []):
        base = re.sub(r" \d+$", "", alias)
        for candidate in (alias, base):
            if candidate in names:
                return candidate
    return None


def plans(cfg, generated) -> list[DesignPlan]:
    """The design lines of a generated basin that a reach carries lumped water past, with what to add to each."""
    if generated is None:
        return []
    lines = {line.name: line.coordinates for line in cfg.outputs.lines}
    elements = {e["name"]: e for e in generated.model["elements"]}
    found: dict[str, list[Part]] = {}
    for junction in generated.junctions:
        if junction.route != ROUTE_REACH or junction.next_junction is None:
            continue
        name = _line_of(elements[junction.junction], set(lines))
        if name is None:
            continue
        sign = _side(lines[name], elements[junction.next_junction]["outlet"])
        if sign == 0.0:
            continue
        take = None
        for line in generated.handbacks:
            if line.element == junction.junction:
                mid = np.mean(np.asarray(line.coordinates, dtype=float), axis=0)
                if _side(lines[name], mid) == sign:
                    take = line.name
        found.setdefault(name, []).append(Part(junction.junction, sign, take))
    return [DesignPlan(name, tuple(parts)) for name, parts in found.items()]


def _read(path: Path, column: str) -> tuple[np.ndarray, np.ndarray]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return np.array([float(r["t_s"]) for r in rows]), np.array([float(r[column]) for r in rows])


def records(
    design: list[DesignPlan], out: Path, t: np.ndarray, grid_flow: dict[str, np.ndarray]
) -> tuple[dict[str, dict[str, np.ndarray]], list[str]]:
    """Each planned line's grid, network and total discharge at the line's own times; and what could not be read."""
    series = Path(out) / "series"
    found, notes = {}, []
    for plan in design:
        q = np.asarray(grid_flow.get(plan.line, np.zeros(t.size)), dtype=float)
        network = np.zeros(t.size)
        for part in plan.parts:
            path = series / f"network_{safe_name(part.element)}.csv"
            if not path.is_file():
                notes.append(f"design line {plan.line}: no network series of {part.element}; its record leaves it out")
                continue
            tn, outflow = _read(path, "outflow_m3s")
            flow = np.interp(t, tn, outflow, left=0.0, right=outflow[-1] if outflow.size else 0.0)
            if part.handback is not None:
                th, taken = _read(series / f"handback_{safe_name(part.handback)}.csv", "inflow_m3s")
                flow = flow - np.interp(t, th, taken, left=0.0, right=taken[-1] if taken.size else 0.0)
            network += part.sign * flow
        found[plan.line] = {GRID: q, NETWORK: network, TOTAL: q + network}
    return found, notes
