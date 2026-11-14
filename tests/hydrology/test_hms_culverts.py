"""Culvert outlets against HEC-HMS 4.12 run headless, and by hand. No project data.

The oracle is W67's cases in ``tests/data/hms_structures`` (W59's test project with new basins, each re-saved by HMS
itself, and HMS's series of each run). ``W67 HMS culverts and drowned weirs/README.md`` holds the numbers and the
probes. Two things are not reproduced, each measured, each its own test here:

- a part-full barrel whose profile reaches the crown inside the barrel reads up to 1.1 cm of pool under HMS's, the
  rule not identified, so outlet-control cases route to 1e-3 of the peak where inlet control holds W59's 3e-4;
- while the pool stands under a fixed tailwater, HMS's books lose a sixtieth of each step's net inflow (as W62's
  armed pump); ours close, so that case is tested on HMS's own pool levels.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.hydrology.test_hms_gates_pumps import _reservoir_with, _unbooked
from tests.hydrology.test_hms_structures import (
    FLOW_TOLERANCE_OF_PEAK,
    LEVEL_TOLERANCE_M,
    STEP_MINUTES,
    load_case,
    reservoir_of,
)
from wadi2d.hydrology import culvert as cv
from wadi2d.hydrology.structures import Culvert, flows_at

CHARTS = [f"culvert_chart_{chart}_{scale}" for chart, scale in cv.INLET_CHARTS
          if (chart, scale) not in ((1, 1), (2, 3), (8, 1), (10, 2))]  # those four have their own cases
INLET_CASES = ["culvert_box_ic", "culvert_box_form2", "culvert_pipe_ic"]
OUTLET_CASES = ["culvert_box_auto", "culvert_box_oc", "culvert_box_tw_part", "culvert_pipe_auto"]
UNDER_TAILWATER = "culvert_box_tw_full"
OUTLET_FLOW_TOLERANCE_OF_PEAK = 1.0e-3
OUTLET_LEVEL_TOLERANCE_M = 4.0e-3
"""The crown-reaching part-full barrel (module docstring): worst steps 7.8e-4 of the peak and 3.1 mm."""
INLET_LAW_TOLERANCE_OF_PEAK = 1.0e-4
OUTLET_LAW_TOLERANCE_OF_PEAK = 1.5e-3
"""At HMS's own pool levels: inlet control within 8e-5 of the peak culvert flow in all 16 charts and scales (HMS's
own iteration), outlet control within 1.4e-3 (the crown-reaching barrel)."""
HAND_TOLERANCE = 1.0e-9
FT = cv.FEET_PER_METRE


def _law_gap(case: str) -> float:
    hms = load_case(case)
    routing = reservoir_of(case)
    structures = (*routing.spillways, *routing.structures)
    index = next(k for k, s in enumerate(structures) if isinstance(s, Culvert))
    tailwater = np.nan if routing.tailwater_m is None else routing.tailwater_m
    flows = flows_at(structures, hms["elevation_m"], (tailwater, np.nan), float(routing.elevations_m[0]))[:, index]
    return float(np.abs(flows - hms["outlet_1"]).max() / hms["outlet_1"].max())


@pytest.mark.parametrize("case", INLET_CASES + CHARTS)
def test_inlet_control_on_hms_own_levels(case: str) -> None:
    assert _law_gap(case) <= INLET_LAW_TOLERANCE_OF_PEAK


@pytest.mark.parametrize("case", [*OUTLET_CASES, UNDER_TAILWATER])
def test_outlet_control_on_hms_own_levels(case: str) -> None:
    assert _law_gap(case) <= OUTLET_LAW_TOLERANCE_OF_PEAK


@pytest.mark.parametrize("case", INLET_CASES + OUTLET_CASES)
def test_culvert_routes_as_hms(case: str) -> None:
    hms = load_case(case)
    run = reservoir_of(case).run(hms["inflow"], STEP_MINUTES)
    peak = np.abs(hms["outflow"]).max()
    flow, level = (FLOW_TOLERANCE_OF_PEAK, LEVEL_TOLERANCE_M) if case in INLET_CASES else (
        OUTLET_FLOW_TOLERANCE_OF_PEAK, OUTLET_LEVEL_TOLERANCE_M)
    assert np.abs(run.main_m3s - hms["outflow"]).max() <= flow * peak
    assert np.abs(run.pool_m - hms["elevation_m"]).max() <= level
    assert np.abs(run.structures_m3s["culvert_1_m3s"] - hms["outlet_1"]).max() <= 2.0 * flow * hms["outlet_1"].max()


def test_under_tailwater_hms_books_do_not_close_and_ours_do() -> None:
    hms = load_case(UNDER_TAILWATER)
    run = reservoir_of(UNDER_TAILWATER).run(hms["inflow"], STEP_MINUTES)
    volume = STEP_MINUTES * 60.0 * np.trapezoid(hms["inflow"])
    under = (hms["elevation_m"][:-1] < 104.0) & (hms["elevation_m"][1:] < 104.0)  # steps wholly under it
    dt = STEP_MINUTES * 60.0
    net = dt * 0.5 * (hms["inflow"][1:] + hms["inflow"][:-1] - hms["outflow"][1:] - hms["outflow"][:-1])
    ratio = np.diff(hms["storage_m3"])[under][1:] / net[under][1:]
    assert np.allclose(ratio, 59.0 / 60.0, atol=1.0e-5)
    assert _unbooked(hms, hms["outflow"], hms["storage_m3"]) < -1.0e-4 * volume
    assert abs(_unbooked(hms, run.main_m3s, run.storage_m3)) < 1.0e-5 * volume


def _box(length: float = 50.0) -> cv.Barrel:
    return cv.Barrel(cv.BOX, 2 * FT, 3 * FT, length * FT, 101.0 * FT, 100.0 * FT, 0.015, 0.4, 1.0)


def test_inlet_control_hand_numbers() -> None:
    barrel, chart = _box(), cv.INLET_CHARTS[8, 1]
    area, rise, slope = 6.0 * FT**2, 2.0 * FT, 0.02
    for ratio in (5.0, 2.0):  # submerged, and unsubmerged form 1
        q = ratio * area * np.sqrt(rise)
        if ratio > cv.SUBMERGED_ABOVE:
            relative = chart.c * ratio**2 + chart.y - 0.5 * slope
        else:
            dc = (q**2 / (cv.GRAVITY_FT * (3 * FT) ** 2)) ** (1.0 / 3.0)
            relative = 1.5 * dc / rise + chart.k * ratio**chart.m - 0.5 * slope
        level = cv.headwater_m(barrel, chart, cv.INLET_CONTROL, 2 * q / cv.CFS_PER_M3S, 2, None)
        assert level == pytest.approx(101.0 + relative * 2.0, rel=HAND_TOLERANCE)


def test_full_barrel_outlet_control_hand_numbers() -> None:
    barrel, chart = _box(), cv.INLET_CHARTS[8, 1]
    flow_m3s, tailwater = 18.0, 102.5  # over the outlet crown: full along the barrel
    velocity_head = (flow_m3s / 6.0) ** 2 / (2.0 * cv.GRAVITY_FT / FT)
    radius = 6.0 / 10.0
    friction = cv.FULL_FRICTION * 0.015**2 * 50.0 * FT / (radius * FT) ** (4.0 / 3.0) * velocity_head
    level = cv.headwater_m(barrel, chart, cv.OUTLET_CONTROL, flow_m3s, 1, tailwater)
    assert level == pytest.approx(tailwater + 1.4 * velocity_head + friction, rel=HAND_TOLERANCE)
    automatic = cv.headwater_m(barrel, chart, cv.AUTOMATIC, flow_m3s, 1, tailwater)
    assert automatic == max(level, cv.headwater_m(barrel, chart, cv.INLET_CONTROL, flow_m3s, 1, tailwater))


def test_culvert_reader_and_refusals(tmp_path) -> None:
    routing = reservoir_of("culvert_pipe_auto")
    pipe = next(s for s in routing.structures if isinstance(s, Culvert))
    assert (pipe.shape, pipe.chart, pipe.scale, pipe.control, pipe.rise_m, pipe.span_m, pipe.barrels) == (
        "Circular", 2, 3, "Automatic", 2.5, 2.5, 2)
    assert (pipe.tailwater_m, pipe.top_m, pipe.length_m, pipe.n) == (101.5, 125.0, 250.0, 0.024)
    with pytest.raises(ValueError, match="shape 'Arch'"):
        _reservoir_with(tmp_path, "culvert_box_ic", "Culvert Shape: Box", "Culvert Shape: Arch")
    with pytest.raises(ValueError, match="no such inlet chart"):
        _reservoir_with(tmp_path, "culvert_box_ic", "Chart Number: 8", "Chart Number: 1")
    with pytest.raises(ValueError, match="keys not read"):
        _reservoir_with(tmp_path, "culvert_box_ic", "Span: 3", "Span: 3\n     Diameter: 3")
    with pytest.raises(ValueError, match="no fall"):
        _reservoir_with(tmp_path, "culvert_box_ic", "Outlet Invert Elevation: 100", "Outlet Invert Elevation: 100.5")
    steep = cv.Barrel(cv.BOX, 3 * FT, 3 * FT, 40 * FT, 105.0 * FT, 100.0 * FT, 0.012, 0.5, 1.0)
    with pytest.raises(ValueError, match="steep barrel"):
        cv.headwater_m(steep, cv.INLET_CHARTS[8, 1], cv.OUTLET_CONTROL, 20.0, 1, None)

