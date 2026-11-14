"""Gate controls beyond Fixed Opening, and drowned gates, against HEC-HMS 4.12 run headless, and by hand.

The oracle is W76's cases in ``tests/data/hms_structures`` (W59's test project, W62's gates, each basin re-saved by HMS
itself, HMS's series of each run, and the hourly percent gage as ``w76_percent.csv``). ``W76 gate controls and breach
estimators/README.md`` holds the numbers and the probes.

- Percent Time Series: HMS's opening at a time is the maximum times the gage's percent, linear in the gage; with it
  W62's law gives HMS's spillway flow at HMS's own pool levels to round-off.
- A tailwater over a gated crest: r = (pool - tailwater) / opening; up to 1 the free flow times W67's submergence
  share, from 1.25 the gate law on the head over the tailwater times sqrt(3), linear between; to round-off on ten runs.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from tests.hydrology.test_hms_gates_pumps import (
    GATE_FLOW_TOLERANCE_OF_PEAK,
    HAND_TOLERANCE,
    LAW_TOLERANCE,
    PEAK_TOLERANCE,
    _reservoir_with,
)
from tests.hydrology.test_hms_structures import DATA, START, STEP_MINUTES, _tables, load_case
from wadi2d.hms import load_basin
from wadi2d.hms.basin import Reservoir as HmsReservoir
from wadi2d.hydrology.from_hms import FlowRecord, ProjectTables, reservoir_from_hms
from wadi2d.hydrology.reservoir import ReservoirOutflowStructures, StructureRun
from wadi2d.hydrology.structure_kernel import GATE_DROWNED_FACTOR, GATE_SQRT_2G, SUBMERGED_SHARE, SUBMERGENCE
from wadi2d.hydrology.structures import SpillwayGate, flows_at

PERCENT_CASES = ["gate_percent_sluice", "gate_percent_radial"]
DROWNED_CASES = [
    "gate_sluice_tw_low", "gate_sluice_tw_lip", "gate_sluice_tw_high", "gate_radial_tw_low", "gate_radial_tw_lip",
    "gate_sluice_tw_a", "gate_sluice_tw_b", "gate_sluice_tw_c", "gate_radial_tw_a", "gate_radial_tw_b",
]
ALL_CASES = PERCENT_CASES + DROWNED_CASES
PERCENT_GAGE = "W76 Percent"
PERCENT_LEVEL_TOLERANCE_M = 5.0e-4
"""W62's 4e-4 m less HMS's unidentified sub-steps near a gate's kink, which a moving opening crosses more often: the
worst step reads 4.4e-4 m; the flow holds W62's 5e-4 of the peak."""
DROWNED_PEAK_TOLERANCE = 6.0e-3
DROWNED_LEVEL_TOLERANCE_M = 3.5e-2
"""HMS's books lose a sixtieth of each step's net inflow while its pool stands between the crest and the tailwater
(8,000 to 43,000 m3 on these runs; W62 and W67 found the same), ours close, so the pool parts by up to 3.4 cm and the
peak by up to 6e-3; the laws are exact at HMS's own levels (the first test)."""
HMS_SIXTIETH = 59.0 / 60.0


def _percent_tables() -> ProjectTables:
    """W59's tables and W76's hourly percent gage as the reader would load it from the project."""
    raw = np.loadtxt(DATA / "w76_percent.csv", delimiter=",", skiprows=1)
    times = np.array([np.datetime64(START + timedelta(hours=float(h)), "s") for h in raw[:, 0]])
    base = _tables()
    return ProjectTables(base.patterns, base.area_reductions, base.paired, {}, {PERCENT_GAGE: FlowRecord(times, raw[:, 1])})


def _routing(case: str) -> ReservoirOutflowStructures:
    basin = load_basin(DATA / f"{case}.basin")
    element = next(e for e in basin.elements if isinstance(e, HmsReservoir))
    routing = reservoir_from_hms(element, _percent_tables(), START).routing
    assert isinstance(routing, ReservoirOutflowStructures)
    return routing


def routed(case: str) -> StructureRun:
    return _routing(case).run(load_case(case)["inflow"], STEP_MINUTES)


def law_at_hms_levels(case: str) -> np.ndarray:
    """The engine's spillway flow at HMS's pool levels, each gate at its opening at each time."""
    hms = load_case(case)
    routing = _routing(case)
    structures = (*routing.spillways, *routing.structures)
    minutes = np.arange(len(hms["elevation_m"])) * STEP_MINUTES
    openings = np.column_stack([
        s.openings_at(minutes) if isinstance(s, SpillwayGate) else np.full(minutes.shape, np.nan) for s in structures
    ])
    tailwater = np.nan if routing.tailwater_m is None else routing.tailwater_m
    flows = flows_at(structures, hms["elevation_m"], (tailwater, np.nan), float(routing.elevations_m[0]), None, openings)
    return flows.sum(axis=1)


@pytest.mark.parametrize("case", ALL_CASES)
def test_gate_law_on_hms_own_levels(case: str) -> None:
    hms = load_case(case)
    assert np.abs(law_at_hms_levels(case) - hms["spill_1"]).max() <= LAW_TOLERANCE * hms["spill_1"].max()


@pytest.mark.parametrize("case", PERCENT_CASES)
def test_percent_time_series_routes_as_hms(case: str) -> None:
    hms = load_case(case)
    run = routed(case)
    peak = np.abs(hms["outflow"]).max()
    assert np.abs(run.main_m3s - hms["outflow"]).max() <= GATE_FLOW_TOLERANCE_OF_PEAK * peak
    assert run.main_m3s.max() == pytest.approx(peak, rel=PEAK_TOLERANCE)
    assert np.abs(run.pool_m - hms["elevation_m"]).max() <= PERCENT_LEVEL_TOLERANCE_M


@pytest.mark.parametrize("case", DROWNED_CASES)
def test_drowned_gate_routes_as_hms(case: str) -> None:
    hms = load_case(case)
    run = routed(case)
    peak = np.abs(hms["outflow"]).max()
    assert run.main_m3s.max() == pytest.approx(peak, rel=DROWNED_PEAK_TOLERANCE)
    assert np.abs(run.pool_m - hms["elevation_m"]).max() <= DROWNED_LEVEL_TOLERANCE_M
    # HMS's sixtieth, where its pool stands between the crest and the tailwater and nothing flows
    dt = STEP_MINUTES * 60.0
    net = dt * 0.5 * (hms["inflow"][1:] + hms["inflow"][:-1] - hms["outflow"][1:] - hms["outflow"][:-1])
    pool, tailwater = hms["elevation_m"], hms["tailwater_m"][0]
    between = (pool[:-1] > 108.0) & (pool[1:] > 108.0) & (pool[1:] < tailwater) & (pool[:-1] < tailwater)
    assert np.diff(hms["storage_m3"])[between] / net[between] == pytest.approx(HMS_SIXTIETH, rel=1.0e-4)


def test_drowned_gate_hand_numbers() -> None:
    crest, opening, tailwater = 108.0, 1.0, 108.6
    sluice = SpillwayGate("Sluice", crest, 1.6, gates=2, width_m=10.0, coefficient=0.6, opening_m=opening)
    # r = 0.3: the free weir (head 0.9 under one opening) times the submergence share at s = 0.667 (1.0);
    # r = 0.2 at s = 0.6 / 0.8 = 0.75 under 0.76: still 1; pool 108.62: s = 0.968, share between rows 0.96 and 0.98.
    pools = np.array([108.9, 108.8, 108.62, 108.6 + 2.0 * opening, 108.6 + 1.125 * opening, 108.5])
    flows = flows_at((sluice,), pools, (tailwater, np.nan), 100.0)[:, 0]
    weir = lambda head: 1.6 * 20.0 * head**1.5  # noqa: E731
    assert flows[0] == pytest.approx(weir(0.9), rel=HAND_TOLERANCE)
    assert flows[1] == pytest.approx(weir(0.8), rel=HAND_TOLERANCE)
    s = 0.6 / 0.62
    assert flows[2] == pytest.approx(weir(0.62) * np.interp(s, SUBMERGENCE, SUBMERGED_SHARE), rel=HAND_TOLERANCE)
    drowned = GATE_DROWNED_FACTOR * 0.6 * 20.0 * opening * GATE_SQRT_2G * (2.0 * opening) ** 0.5
    assert flows[3] == pytest.approx(drowned, rel=HAND_TOLERANCE)
    head = 0.6 + 1.125
    free = 0.6 * 20.0 * opening * GATE_SQRT_2G * head**0.5  # head / opening 1.725: the free gate law
    high = GATE_DROWNED_FACTOR * 0.6 * 20.0 * opening * GATE_SQRT_2G * 1.125**0.5
    assert flows[4] == pytest.approx(free + 0.5 * (high - free), rel=HAND_TOLERANCE)
    assert flows[5] == 0.0
    assert pytest.approx(np.sqrt(3.0), rel=HAND_TOLERANCE) == GATE_DROWNED_FACTOR


def test_percent_schedule_hand_numbers() -> None:
    gate = SpillwayGate(
        "Sluice", 108.0, 1.6, gates=2, width_m=10.0, coefficient=0.6, opening_m=2.0, maximum_opening_m=2.0,
        schedule_minutes=(0.0, 60.0, 120.0), schedule_percent=(100.0, 50.0, 25.0),
    )
    assert gate.openings_at(np.array([0.0, 30.0, 90.0, 120.0])) == pytest.approx([2.0, 1.5, 0.75, 0.5])
    fixed = SpillwayGate("Sluice", 108.0, 1.6, gates=2, width_m=10.0, coefficient=0.6, opening_m=0.75)
    pools = np.array([110.5])
    at_90 = flows_at((gate,), pools, (np.nan, np.nan), 100.0, None, gate.openings_at(np.array([[90.0]])))
    assert at_90[0, 0] == pytest.approx(flows_at((fixed,), pools, (np.nan, np.nan), 100.0)[0, 0], rel=HAND_TOLERANCE)
    with pytest.raises(ValueError, match="pass the percent schedule"):
        gate.openings_at(np.array([0.0, 125.0]))
    with pytest.raises(ValueError, match="percents from 0 to 100"):
        SpillwayGate("Sluice", 108.0, 1.6, gates=2, width_m=10.0, coefficient=0.6, opening_m=2.0,
                     maximum_opening_m=2.0, schedule_minutes=(0.0, 60.0), schedule_percent=(100.0, 120.0))


def test_fixed_gates_without_tailwater_unchanged() -> None:
    """A fixed opening reads the packed factor as before: W62's runs give the same bits with a NaN opening given."""
    case = "gate_two"
    hms = load_case(case)
    routing = _routing(case)
    structures = (*routing.spillways, *routing.structures)
    levels = hms["elevation_m"]
    plain = flows_at(structures, levels, (np.nan, np.nan), 100.0)
    nan = flows_at(structures, levels, (np.nan, np.nan), 100.0, None, np.full((len(levels), len(structures)), np.nan))
    assert np.array_equal(plain, nan)
    below = flows_at(structures, levels, (107.9, np.nan), 100.0)
    assert np.array_equal(plain, below)


def test_gate_control_refusals(tmp_path) -> None:
    pattern = (
        "Gate Control: Percent Annual Pattern\n     Maximum Gate Opening: 2\n     Percent Pattern Name: W76 Annual"
    )
    with pytest.raises(ValueError, match=r"Percent Annual Pattern.*not identify"):
        _reservoir_with(tmp_path, "gate_sluice", "Gate Control: Fixed Opening\n     Gate Opening: 1.5", pattern)
    with pytest.raises(ValueError, match=r"Adjustable Gate Control.*rule-based"):
        _reservoir_with(tmp_path, "gate_sluice", "Gate Control: Fixed Opening\n     Gate Opening: 1.5",
                        "Gate Control: Adjustable Gate Control")
    with pytest.raises(ValueError, match="percent gage 'W76 Percent' is not available"):
        _reservoir_with(tmp_path, "gate_percent_sluice", "Number Gates: 2", "Number Gates: 2")
    element = next(
        e for e in load_basin(DATA / "gate_percent_sluice.basin").elements if isinstance(e, HmsReservoir)
    )
    with pytest.raises(ValueError, match="needs the run's start date"):
        reservoir_from_hms(element, _percent_tables(), None)
    late = reservoir_from_hms(element, _percent_tables(), START - timedelta(hours=1)).routing
    with pytest.raises(ValueError, match="pass the percent schedule"):
        late.run(load_case("gate_percent_sluice")["inflow"], STEP_MINUTES)
