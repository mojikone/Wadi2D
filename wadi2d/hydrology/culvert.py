"""HEC-HMS 4.12's culvert outlet, box and circular barrels: headwater from flow by FHWA HDS-5 inlet control and an
energy balance through the barrel for outlet control, and the rating a reservoir routes on.

Interface: :data:`INLET_CHARTS`, :func:`inlet_headwater_m`, :func:`outlet_headwater_m`, :func:`headwater_m`,
:func:`rating`. Everything is computed in feet and cfs inside, as HMS's own routine is (its constants are 32.174 and
1.48592, ``hms.jar`` ``culvert/model/routine``), with metres and m3/s at the interface.

Measured against HMS's output at HMS's own pool levels (W67), not taken from the manual alone:

- inlet control is HDS-5 per chart and scale with velocities zero: unsubmerged up to Q/(A D^0.5) = 3.5, submerged
  from 4.0, and between them the two forms at the same ratio blended linearly in it (not the two end values
  joined); form 1 HW/D = Hc/D + K X^M - 0.5 S, form 2 HW/D = K X^M, submerged
  HW/D = c X^2 + Y - 0.5 S for form 1 charts and with no slope term for form 2 charts;
  a mitered inlet (chart 2 scale 2) takes +0.7 S;
- HMS's own coefficients, each of the 16 charts and scales here measured; two differ from HDS-5's print: chart 1
  scale 2 has K 0.0078, not 0.0018, and chart 8 scale 1 has Y 0.86, not 0.81;
- outlet control: full barrel, pool = tailwater + (ke + kx) V^2/2g + 29.1673 n^2 L / R^(4/3) V^2/2g once the
  tailwater reaches the outlet crown; otherwise a direct-step profile upstream from the higher of critical depth and
  the tailwater, pool = inlet invert + depth + (1 + ke) V^2/2g, the barrel full from where the profile reaches its
  crown; the one difference left is there, up to 1.1 cm of pool, not identified (W67);
- Automatic, the higher headwater of the two at a flow.

A culvert is routed as a rating: the headwater of a ladder of flows at the reservoir's fixed tailwater, inverted,
since the headwater rises with the flow. HMS warns that a culvert computes 10 to 20 times slower than an orifice;
here the cost is paid once, when the reservoir packs its structures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

FEET_PER_METRE = 1.0 / 0.3048
CFS_PER_M3S = FEET_PER_METRE**3
GRAVITY_FT = 32.174
MANNING_FT = 1.48592
FULL_FRICTION = 29.1673
"""HMS's full-barrel friction, h_f = 29.1673 n^2 L / R^(4/3) V^2 / 2g (``C_FULL``)."""
UNSUBMERGED_BELOW = 3.5
SUBMERGED_ABOVE = 4.0
SLOPE_TERM = -0.5
MITERED_SLOPE_TERM = 0.7
BOX = "Box"
CIRCULAR = "Circular"
INLET_CONTROL = "Inlet Control"
OUTLET_CONTROL = "Outlet Control"
AUTOMATIC = "Automatic"
CONTROLS = (INLET_CONTROL, OUTLET_CONTROL, AUTOMATIC)
RATING_FLOWS = 2000
"""Flows in a culvert's rating, spaced as the 1.5 power from none to the flow at the pool table's top."""
PROFILE_STEPS = 400
"""Depth increments of the direct-step profile through a part-full barrel."""
BISECTIONS = 80


@dataclass(frozen=True)
class InletChart:
    """One HDS-5 chart and scale: its shape, form (1 or 2), K, M, c and Y, English units."""

    shape: str
    form: int
    k: float
    m: float
    c: float
    y: float
    slope: float = SLOPE_TERM
    """Ks of the slope term Ks S, form 1 only: -0.5, +0.7 for a mitered inlet."""


INLET_CHARTS: dict[tuple[int, int], InletChart] = {
    # circular concrete: square edge with headwall, groove end with headwall, groove end projecting
    (1, 1): InletChart(CIRCULAR, 1, 0.0098, 2.0, 0.0398, 0.67),
    (1, 2): InletChart(CIRCULAR, 1, 0.0078, 2.0, 0.0292, 0.74),
    (1, 3): InletChart(CIRCULAR, 1, 0.0045, 2.0, 0.0317, 0.69),
    # corrugated metal pipe: headwall, mitered to the slope, projecting
    (2, 1): InletChart(CIRCULAR, 1, 0.0078, 2.0, 0.0379, 0.69),
    (2, 2): InletChart(CIRCULAR, 1, 0.0210, 1.33, 0.0463, 0.75, MITERED_SLOPE_TERM),
    (2, 3): InletChart(CIRCULAR, 1, 0.0340, 1.50, 0.0553, 0.54),
    # circular with a beveled ring: 45 and 33.7 degree bevels
    (3, 1): InletChart(CIRCULAR, 1, 0.0018, 2.50, 0.0300, 0.74),
    (3, 2): InletChart(CIRCULAR, 1, 0.0018, 2.50, 0.0243, 0.83),
    # box with flared wingwalls: 30 to 75 degrees, 90 and 15 degrees, 0 degrees
    (8, 1): InletChart(BOX, 1, 0.026, 1.0, 0.0347, 0.86),
    (8, 2): InletChart(BOX, 1, 0.061, 0.75, 0.0400, 0.80),
    (8, 3): InletChart(BOX, 1, 0.061, 0.75, 0.0423, 0.82),
    # box with flared wingwalls and a beveled top edge: 45 degrees, 18 to 33.7 degrees
    (9, 1): InletChart(BOX, 2, 0.510, 0.667, 0.0309, 0.80),
    (9, 2): InletChart(BOX, 2, 0.486, 0.667, 0.0249, 0.83),
    # box with a 90 degree headwall: 3/4 inch chamfers, 45 degree bevels, 33.7 degree bevels
    (10, 1): InletChart(BOX, 2, 0.515, 0.667, 0.0375, 0.79),
    (10, 2): InletChart(BOX, 2, 0.495, 0.667, 0.0314, 0.82),
    (10, 3): InletChart(BOX, 2, 0.486, 0.667, 0.0252, 0.865),
}


@dataclass(frozen=True)
class Barrel:
    """One barrel in feet: shape, rise D and span B (the diameter twice for a pipe), length, inverts, n, losses."""

    shape: str
    rise: float
    span: float
    length: float
    inlet: float
    outlet: float
    n: float
    entrance: float
    exit: float

    @property
    def slope(self) -> float:
        return (self.inlet - self.outlet) / self.length

    @property
    def full_area(self) -> float:
        return self.rise * self.span if self.shape == BOX else math.pi * self.rise**2 / 4.0

    @property
    def full_radius(self) -> float:
        if self.shape == BOX:
            return self.full_area / (2.0 * (self.rise + self.span))
        return self.rise / 4.0

    def section(self, depth: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Area, top width and wetted perimeter at depths under the crown."""
        depth = np.clip(depth, 1e-12, self.rise * (1.0 - 1e-12))
        if self.shape == BOX:
            return self.span * depth, np.full_like(depth, self.span), self.span + 2.0 * depth
        radius = self.rise / 2.0
        theta = 2.0 * np.arccos(1.0 - depth / radius)
        return (radius**2 * (theta - np.sin(theta)) / 2.0, 2.0 * radius * np.sin(theta / 2.0), radius * theta)


def _bisect(function, low: float, high: float) -> float:
    for _ in range(BISECTIONS):
        middle = 0.5 * (low + high)
        if function(middle) > 0.0:
            high = middle
        else:
            low = middle
    return 0.5 * (low + high)


def critical_depth(barrel: Barrel, flow: float) -> float:
    """Critical depth, ft, capped at the rise where none exists under the crown."""
    def excess(depth: float) -> float:
        area, top, _ = barrel.section(np.array([depth]))
        return float(area[0] ** 3 / top[0]) - flow**2 / GRAVITY_FT
    if flow <= 0.0:
        return 0.0
    if excess(barrel.rise * (1.0 - 1e-9)) < 0.0:
        return barrel.rise
    return _bisect(excess, 0.0, barrel.rise)


def normal_depth(barrel: Barrel, flow: float) -> float:
    """Normal depth, ft, the rise where the barrel cannot carry the flow part full, infinite on no slope."""
    if barrel.slope <= 0.0:
        return math.inf
    def excess(depth: float) -> float:
        area, _, perimeter = barrel.section(np.array([depth]))
        return float(MANNING_FT / barrel.n * area[0] * (area[0] / perimeter[0]) ** (2.0 / 3.0)) * math.sqrt(
            barrel.slope) - flow
    if excess(barrel.rise * (1.0 - 1e-9)) < 0.0:
        return barrel.rise
    return _bisect(excess, 0.0, barrel.rise)


def _inlet(barrel: Barrel, chart: InletChart, flow: float) -> float:
    """Headwater over the inlet invert, ft, per barrel flow ``flow`` cfs."""
    ratio = flow / (barrel.full_area * math.sqrt(barrel.rise))
    slope_term = chart.slope * barrel.slope if chart.form == 1 else 0.0

    def unsubmerged(x: float) -> float:
        if chart.form == 2:
            return chart.k * x**chart.m
        q = x * barrel.full_area * math.sqrt(barrel.rise)
        depth = critical_depth(barrel, q)
        area, top, _ = barrel.section(np.array([depth]))
        head = depth + float(area[0] / (2.0 * top[0])) if depth < barrel.rise else depth
        return head / barrel.rise + chart.k * x**chart.m + slope_term

    def submerged(x: float) -> float:
        return chart.c * x * x + chart.y + slope_term

    if ratio <= UNSUBMERGED_BELOW:
        relative = unsubmerged(ratio)
    elif ratio >= SUBMERGED_ABOVE:
        relative = submerged(ratio)
    else:
        share = (ratio - UNSUBMERGED_BELOW) / (SUBMERGED_ABOVE - UNSUBMERGED_BELOW)
        low, high = unsubmerged(ratio), submerged(ratio)
        relative = low + share * (high - low)
    return relative * barrel.rise


def _full(barrel: Barrel, flow: float, length: float) -> tuple[float, float]:
    """Velocity head and friction loss of the full barrel over ``length``, ft."""
    head = (flow / barrel.full_area) ** 2 / (2.0 * GRAVITY_FT)
    return head, FULL_FRICTION * barrel.n**2 * length / barrel.full_radius ** (4.0 / 3.0) * head


def _outlet(barrel: Barrel, flow: float, tailwater: float) -> tuple[float, bool]:
    """Headwater elevation, ft, by the energy balance from the outlet, ``tailwater`` -inf for none; and whether it
    came from a steep barrel (normal under critical depth), critical depth at the inlet, a reading not measured."""
    if flow <= 0.0:
        return (max(barrel.inlet, tailwater), False)
    if tailwater - barrel.outlet >= barrel.rise:
        head, friction = _full(barrel, flow, barrel.length)
        return (tailwater + (barrel.entrance + barrel.exit) * head + friction, False)
    critical = critical_depth(barrel, flow)
    start = max(critical, tailwater - barrel.outlet)
    if start >= barrel.rise:
        head, friction = _full(barrel, flow, barrel.length)
        return (barrel.outlet + barrel.rise + (1.0 + barrel.entrance) * head + friction, False)
    normal = normal_depth(barrel, flow)
    if normal <= critical:
        area, _, _ = barrel.section(np.array([critical]))
        return barrel.inlet + critical + (1.0 + barrel.entrance) * flow**2 / (2.0 * GRAVITY_FT * area[0] ** 2), True
    # direct step upstream from the outlet depth toward the normal depth, or to the crown
    target = min(normal, barrel.rise) if normal != start else start
    depths = start + (target - start) * (1.0 - (1.0 - np.linspace(0.0, 1.0, PROFILE_STEPS + 1)) ** 2)
    if normal >= barrel.rise or normal > start:
        depths = np.minimum(depths, barrel.rise)
    area, _, perimeter = barrel.section(depths)
    energy = depths + flow**2 / (2.0 * GRAVITY_FT * area**2)
    friction = (flow * barrel.n / (MANNING_FT * area * (area / perimeter) ** (2.0 / 3.0))) ** 2
    mean = 0.5 * (friction[1:] + friction[:-1])
    with np.errstate(divide="ignore", invalid="ignore"):
        steps = np.diff(energy) / (mean - barrel.slope)  # upstream: dE = (Sf - S0) dx
    steps = np.where(np.isfinite(steps) & (steps > 0.0), steps, 0.0)
    reach = np.concatenate(([0.0], np.cumsum(steps)))
    if reach[-1] < barrel.length and depths[-1] >= barrel.rise * (1.0 - 1e-9):
        crown = barrel.outlet + barrel.slope * reach[-1] + barrel.rise
        head, friction_full = _full(barrel, flow, barrel.length - reach[-1])
        return (crown + (1.0 + barrel.entrance) * head + friction_full, False)
    depth = float(np.interp(barrel.length, reach, depths)) if reach[-1] >= barrel.length else float(depths[-1])
    area_in, _, _ = barrel.section(np.array([depth]))
    return (barrel.inlet + depth + (1.0 + barrel.entrance) * flow**2 / (2.0 * GRAVITY_FT * area_in[0] ** 2), False)


def headwater_m(
    barrel: Barrel, chart: InletChart, control: str, flow_m3s: float, barrels: int, tailwater_m: float | None
) -> float:
    """The pool elevation, m, that passes ``flow_m3s`` through ``barrels`` barrels: inlet control, outlet control, or
    Automatic, the higher of the two (the lower flow at a pool)."""
    flow = flow_m3s * CFS_PER_M3S / barrels
    tailwater = -math.inf if tailwater_m is None else tailwater_m * FEET_PER_METRE
    levels = []
    if control in (INLET_CONTROL, AUTOMATIC):
        levels.append(barrel.inlet + _inlet(barrel, chart, flow) if flow > 0.0 else barrel.inlet)
    if control in (OUTLET_CONTROL, AUTOMATIC):
        level, steep = _outlet(barrel, flow, tailwater)
        if steep and level > max(levels, default=-math.inf):
            raise ValueError(f"culvert: outlet control governs on a steep barrel at {flow_m3s:.3f} m3/s; HMS's "
                             "rule there was not measured")
        levels.append(level)
    return max(levels) / FEET_PER_METRE


def rating(
    barrel: Barrel, chart: InletChart, control: str, barrels: int, tailwater_m: float | None, top_m: float
) -> tuple[np.ndarray, np.ndarray]:
    """Pool elevations, m, and flows, m3/s, rising, from no flow to past ``top_m``: the culvert as a rating."""
    def level(flow: float) -> float:
        return headwater_m(barrel, chart, control, flow, barrels, tailwater_m)
    still = level(0.0)
    if top_m <= still:
        return np.array([still, still + 1.0]), np.zeros(2)
    highest = 1.0
    while level(highest) < top_m:
        highest *= 2.0
    flows = highest * np.linspace(0.0, 1.0, RATING_FLOWS + 1) ** 1.5
    levels = np.array([level(float(flow)) for flow in flows])
    levels = np.maximum.accumulate(levels)
    keep = np.concatenate(([True], np.diff(levels) > 0.0))
    return levels[keep], flows[keep]
