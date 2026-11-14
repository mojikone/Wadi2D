"""Drowned broad-crested spillways and level dam tops against HEC-HMS 4.12 run headless, and by hand. No project data.

The oracle is W59's ``level_dam_tw`` and W67's ``damtop_drowned``, ``broad_drowned`` and ``broad_drowned_high`` in
``tests/data/hms_structures``: a fixed tailwater over the crest, the pool passing through every submergence. HMS
reduces the free flow by one tabulated share on the submergence (``structure_kernel.SUBMERGENCE``), the same for both
structures, and the table gives HMS's flows at HMS's own pool levels to round-off. ``W67 HMS culverts and drowned
weirs/README.md`` holds the numbers. Two things in HMS are not reproduced, each measured, each its own test:

- near full submergence the outflow changes by about 16,000 m3/s per metre of pool, and HMS takes sub-steps there that
  the 0.1 m bisection does not ask for (its rule not identified; 1 mm sub-steps bring ``level_dam_tw`` from 3.8 mm
  to 0.2 mm of HMS's pool), so that case is held on its pool and peak, not on the flow at the stiff steps;
- while a broad-crested spillway's pool stands between its crest and the tailwater, HMS's books lose a sixtieth of each
  step's net inflow (as W62's armed pump); ours close.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.hydrology.test_hms_gates_pumps import _unbooked
from tests.hydrology.test_hms_structures import (
    FLOW_TOLERANCE_OF_PEAK,
    LAW_TOLERANCE,
    STEP_MINUTES,
    load_case,
    reservoir_of,
)
from wadi2d.hydrology.reservoir import ReservoirOutflowStructures, Spillway
from wadi2d.hydrology.structure_kernel import SUBMERGED_SHARE
from wadi2d.hydrology.structures import LevelDamTop, flows_at

CASES = {"level_dam_tw": "damtop_1", "damtop_drowned": "damtop_1", "broad_drowned": "spill_1",
         "broad_drowned_high": "spill_1"}
DROWNED_LEVEL_TOLERANCE_M = 3.0e-4
STIFF_LEVEL_TOLERANCE_M = 4.0e-3
STIFF_PEAK_TOLERANCE = 2.0e-3
HAND_TOLERANCE = 1.0e-9
DT_S = STEP_MINUTES * 60.0


@pytest.mark.parametrize("case", CASES)
def test_drowned_law_on_hms_own_levels(case: str) -> None:
    hms = load_case(case)
    routing = reservoir_of(case)
    structures = (*routing.spillways, *routing.structures)
    flows = flows_at(structures, hms["elevation_m"], (routing.tailwater_m, np.nan), float(routing.elevations_m[0]))
    index = 0 if CASES[case] == "spill_1" else len(structures) - 1
    theirs = hms[CASES[case]]
    assert np.abs(flows[:, index] - theirs).max() <= LAW_TOLERANCE * theirs.max()


def test_drowned_dam_top_routes_as_hms() -> None:
    hms = load_case("damtop_drowned")
    run = reservoir_of("damtop_drowned").run(hms["inflow"], STEP_MINUTES)
    assert np.abs(run.main_m3s - hms["outflow"]).max() <= FLOW_TOLERANCE_OF_PEAK * hms["outflow"].max()
    assert np.abs(run.pool_m - hms["elevation_m"]).max() <= DROWNED_LEVEL_TOLERANCE_M


def test_near_full_submergence_pool_and_peak_as_hms() -> None:
    hms = load_case("level_dam_tw")
    run = reservoir_of("level_dam_tw").run(hms["inflow"], STEP_MINUTES)
    assert np.abs(run.pool_m - hms["elevation_m"]).max() <= STIFF_LEVEL_TOLERANCE_M
    assert run.main_m3s.max() == pytest.approx(hms["outflow"].max(), rel=STIFF_PEAK_TOLERANCE)


@pytest.mark.parametrize("case", ["broad_drowned", "broad_drowned_high"])
def test_spillway_under_tailwater_hms_books_do_not_close_and_ours_do(case: str) -> None:
    hms = load_case(case)
    run = reservoir_of(case).run(hms["inflow"], STEP_MINUTES)
    z, tailwater = hms["elevation_m"], reservoir_of(case).tailwater_m
    between = (z[:-1] > 108.0) & (z[1:] > 108.0) & (z[:-1] < tailwater) & (z[1:] < tailwater)
    net = DT_S * 0.5 * (hms["inflow"][1:] + hms["inflow"][:-1] - hms["outflow"][1:] - hms["outflow"][:-1])
    assert np.allclose(np.diff(hms["storage_m3"])[between] / net[between], 59.0 / 60.0, atol=1.0e-5)
    ours = DT_S * 0.5 * (hms["inflow"][1:] + hms["inflow"][:-1] - run.main_m3s[1:] - run.main_m3s[:-1])
    assert np.median(np.diff(run.storage_m3)[between] / ours[between]) == pytest.approx(1.0, abs=1.0e-6)
    volume = DT_S * np.trapezoid(hms["inflow"])
    assert _unbooked(hms, hms["outflow"], hms["storage_m3"]) < -1.0e-4 * volume


def test_drowned_hand_numbers() -> None:
    top = LevelDamTop(109.5, 150.0, 1.7)
    spill = Spillway(108.0, 60.0, 1.6)
    head = 1.0
    for submergence, share in [(0.5, 1.0), (0.76, 1.0), (0.86, 0.9725), (0.97, 0.6475), (0.999, 0.076), (1.0, 0.0),
                               (1.2, 0.0)]:
        level = np.array([109.5 + head])
        tailwater = 109.5 + submergence * head
        flow = flows_at((top,), level, (tailwater, np.nan), 100.0)[0, 0]
        assert flow == pytest.approx(share * 1.7 * 150.0 * head**1.5, rel=HAND_TOLERANCE, abs=HAND_TOLERANCE)
    spilled = flows_at((spill,), np.array([110.0]), (109.9, np.nan), 100.0)[0, 0]  # s 0.95: between 0.94 and 0.96
    assert spilled == pytest.approx(0.77 * 1.6 * 60.0 * 2.0**1.5, rel=HAND_TOLERANCE)
    assert np.all(np.diff(SUBMERGED_SHARE) < 0.0) and SUBMERGED_SHARE[0] == 1.0 and SUBMERGED_SHARE[-1] == 0.0
    # a tailwater over a plain crest now routes; the auxiliary outlet still sees none
    z = np.linspace(100.0, 110.0, 11)
    ReservoirOutflowStructures(z, np.full(11, 1.0e5), (Spillway(104.0, 10.0, 1.6),), 100.0, tailwater_m=104.5)
