"""Gated spillways and pumps against HEC-HMS 4.12 run headless, and by hand. No project data.

The oracle is W62's cases in ``tests/data/hms_structures`` (W59's test project with new basins, each re-saved by HMS
itself, and HMS's series of each run). ``W62 HMS culverts gates pumps/README.md`` holds the numbers and the probes.

Two things in HMS are not reproduced, each measured, each its own test here:

- near a gate's change of regime HMS takes steps of 7 s that the 0.1 m bisection does not ask for; its rule was not
  identified, so the gate cases route to 4.1e-4 of the peak at worst against W59's 3e-4, every law exact;
- while a pump is off and the pool stands above its intake, HMS's books lose a sixtieth of each step's net inflow
  (books of 19,000 to 36,000 m3 that do not close); ours close, so those runs part from HMS by the pool that water
  would have filled, and the switching is tested on HMS's own pool levels instead.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.hydrology.test_hms_structures import (
    DATA,
    FLOW_TOLERANCE_OF_PEAK,
    LEVEL_TOLERANCE_M,
    STEP_MINUTES,
    _tables,
    load_case,
    reservoir_of,
)
from wadi2d.hms import load_basin
from wadi2d.hms.basin import Reservoir as HmsReservoir
from wadi2d.hydrology.from_hms import reservoir_from_hms
from wadi2d.hydrology.reservoir import ReservoirOutflowStructures
from wadi2d.hydrology.structure_kernel import GATE_SQRT_2G, PUMP, _switch_pumps
from wadi2d.hydrology.structures import Pump, SpillwayGate, flows_at, pack_all

GATE_CASES = ["gate_sluice", "gate_radial", "gate_two"]
PUMP_CASES = [
    "pump", "pump_tw", "pump_closed", "pump_cycle", "pump_intake", "pump_times", "pump_rest", "pump_on_band",
    "pump_off_band",
]
GATE_FLOW_TOLERANCE_OF_PEAK = 5.0e-4
GATE_LEVEL_TOLERANCE_M = 4.0e-4
"""HMS's sub-steps near a gate's kink are not identified (module docstring); the worst step reads 4.1e-4 of the peak
and 3.0e-4 m."""
PEAK_TOLERANCE = 1.0e-4
LAW_TOLERANCE = 1.0e-9
HAND_TOLERANCE = 1.0e-12
BISECTED_STEP_M = 0.1
"""A step that moves HMS's pool more than this was cut in parts, whose starts its series do not show."""
DT_S = STEP_MINUTES * 60.0
CLOSED_AREA_M2 = 8.5e5
"""Pool area near pump_closed's switch level, 106.5 m, to turn HMS's unbooked volume into a level."""


def _unbooked(hms: dict[str, np.ndarray], outflow: np.ndarray, storage: np.ndarray) -> float:
    change = np.diff(storage) - DT_S * 0.5 * (hms["inflow"][1:] + hms["inflow"][:-1] - outflow[1:] - outflow[:-1])
    return float(change.sum())


@pytest.mark.parametrize("case", GATE_CASES)
def test_gated_spillway_routes_as_hms(case: str) -> None:
    hms = load_case(case)
    run = reservoir_of(case).run(hms["inflow"], STEP_MINUTES)
    peak = np.abs(hms["outflow"]).max()
    assert np.abs(run.main_m3s - hms["outflow"]).max() <= GATE_FLOW_TOLERANCE_OF_PEAK * peak
    assert run.main_m3s.max() == pytest.approx(hms["outflow"].max(), rel=PEAK_TOLERANCE)
    assert np.abs(run.pool_m - hms["elevation_m"]).max() <= GATE_LEVEL_TOLERANCE_M
    gates = sum(flow for name, flow in run.structures_m3s.items() if name.startswith("gate"))
    assert np.abs(gates - hms["spill_1"]).max() <= GATE_FLOW_TOLERANCE_OF_PEAK * peak


@pytest.mark.parametrize("case", GATE_CASES)
def test_gate_law_on_hms_own_levels(case: str) -> None:
    """Weir, transition and gate regimes all occur in each case; the law gives HMS's spillway flow to round-off."""
    hms = load_case(case)
    routing = reservoir_of(case)
    structures = (*routing.spillways, *routing.structures)
    flows = flows_at(structures, hms["elevation_m"], (np.nan, np.nan), float(routing.elevations_m[0])).sum(axis=1)
    assert np.abs(flows - hms["spill_1"]).max() <= LAW_TOLERANCE * hms["spill_1"].max()


def test_gate_hand_numbers() -> None:
    sluice = SpillwayGate("Sluice", 108.0, 1.6, gates=2, width_m=10.0, coefficient=0.6, opening_m=1.5)
    radial = SpillwayGate(
        "Radial", 108.0, 1.6, gates=2, width_m=10.0, coefficient=0.7, opening_m=1.5, trunnion_height_m=3.0,
        trunnion_exponent=0.16, opening_exponent=0.72, head_exponent=0.62,
    )
    weir_head, gate_head, mid_head = 1.2, 2.5, 1.5 * 1.125  # under one opening, over 1.25, half way between
    flows = flows_at((sluice, radial), np.array([108.0 + weir_head, 108.0 + gate_head, 108.0 + mid_head, 107.0]),
                     (np.nan, np.nan), 100.0)
    weir = 1.6 * 20.0 * weir_head**1.5
    assert flows[0] == pytest.approx([weir, weir], rel=HAND_TOLERANCE)
    sluice_gate = 0.6 * 20.0 * 1.5 * GATE_SQRT_2G * gate_head**0.5
    radial_gate = 0.7 * GATE_SQRT_2G * 20.0 * 3.0**0.16 * 1.5**0.72 * gate_head**0.62
    assert flows[1] == pytest.approx([sluice_gate, radial_gate], rel=HAND_TOLERANCE)
    mid_weir = 1.6 * 20.0 * mid_head**1.5
    mid_gate = 0.6 * 20.0 * 1.5 * GATE_SQRT_2G * mid_head**0.5
    assert flows[2, 0] == pytest.approx(0.5 * (mid_weir + mid_gate), rel=HAND_TOLERANCE)
    assert flows[3].tolist() == [0.0, 0.0]


def _reservoir_with(tmp_path, case: str, old: str, new: str) -> ReservoirOutflowStructures:
    text = (DATA / f"{case}.basin").read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / f"{case}.basin"
    path.write_text(text.replace(old, new), encoding="utf-8")
    element = next(e for e in load_basin(path).elements if isinstance(e, HmsReservoir))
    return reservoir_from_hms(element, _tables()).routing


def test_gate_reader_refusals(tmp_path) -> None:
    with pytest.raises(ValueError, match="crest of 30"):
        _reservoir_with(tmp_path, "gate_sluice", "Spillway Crest Length: 20", "Spillway Crest Length: 30")
    with pytest.raises(ValueError, match=r"Percent Pattern.* is not supported"):
        _reservoir_with(tmp_path, "gate_sluice", "Gate Control: Fixed Opening", "Gate Control: Percent Pattern")
    with pytest.raises(ValueError, match="keys not read"):
        _reservoir_with(tmp_path, "gate_radial", "Head Exponent: 0.62", "Head Exponent: 0.62\n     Gate Drift: 1")


def test_pump_head_law_on_hms_own_levels() -> None:
    """While on, each case's pump flow is the table at discharge elevation - pool + loss, times the units, to the
    last digit; a fixed tailwater under the intake changes nothing (pump against pump_tw)."""
    for case in PUMP_CASES:
        hms = load_case(case)
        routing = reservoir_of(case)
        structures = (*routing.spillways, *routing.structures)
        index = next(k for k, s in enumerate(structures) if isinstance(s, Pump))
        on = hms["pump_1"] > 0.0
        flows = flows_at(structures, hms["elevation_m"][on], (np.nan, np.nan), 100.0)[:, index]
        assert np.abs(flows - hms["pump_1"][on]).max() <= LAW_TOLERANCE * hms["pump_1"].max(), case
    assert np.array_equal(load_case("pump")["outflow"], load_case("pump_tw")["outflow"])


@pytest.mark.parametrize("case", PUMP_CASES)
def test_pump_switches_as_hms_on_its_own_levels(case: str) -> None:
    """The state machine fed HMS's pool at each step start reproduces HMS's on and off at every step, minimum run
    and rest (minutes) and the half-millimetre switch-on band included; only a step HMS cut in parts can differ."""
    hms = load_case(case)
    routing = reservoir_of(case)
    arrays = pack_all((*routing.spillways, *routing.structures))
    pump = int(np.flatnonzero(arrays.kinds == PUMP)[0])
    active = np.where(arrays.kinds == PUMP, 0.0, 1.0)
    since = np.full(len(arrays.kinds), -np.inf)
    z = hms["elevation_m"]
    ours = np.zeros(len(z), dtype=bool)
    _switch_pumps(z[0], 0.0, arrays.kinds, arrays.parameters, active, since)
    ours[0] = active[pump] > 0.0
    for step in range(1, len(z)):
        _switch_pumps(z[step - 1], (step - 1) * DT_S, arrays.kinds, arrays.parameters, active, since)
        ours[step] = active[pump] > 0.0
    differ = np.flatnonzero(ours != (hms["pump_1"] > 0.0))
    assert np.all(np.abs(z[differ] - z[differ - 1]) > BISECTED_STEP_M), (case, differ.tolist())


def test_pump_routes_as_hms_where_its_books_close() -> None:
    """pump_closed: intake, off and on at one level, so the pool never stands armed above the intake; the outflow
    matches HMS within W59's tolerance and the pool within it plus HMS's own unbooked volume over the pool area."""
    hms = load_case("pump_closed")
    run = reservoir_of("pump_closed").run(hms["inflow"], STEP_MINUTES)
    peak = np.abs(hms["outflow"]).max()
    assert np.abs(run.main_m3s - hms["outflow"]).max() <= FLOW_TOLERANCE_OF_PEAK * peak
    unbooked = abs(_unbooked(hms, hms["outflow"], hms["storage_m3"]))
    assert np.abs(run.pool_m - hms["elevation_m"]).max() <= LEVEL_TOLERANCE_M + unbooked / CLOSED_AREA_M2
    assert np.array_equal(run.structures_m3s["pump_1_m3s"] > 0.0, hms["pump_1"] > 0.0)


@pytest.mark.parametrize("case", ["pump_cycle", "pump_times", "pump_off_band"])
def test_pump_armed_hms_books_do_not_close_and_ours_do(case: str) -> None:
    hms = load_case(case)
    run = reservoir_of(case).run(hms["inflow"], STEP_MINUTES)
    volume = DT_S * np.trapezoid(hms["inflow"])
    assert _unbooked(hms, hms["outflow"], hms["storage_m3"]) < -1.0e-3 * volume
    assert abs(_unbooked(hms, run.main_m3s, run.storage_m3)) < 1.0e-4 * volume


def test_pump_hand_numbers_and_refusals() -> None:
    heads, flows = np.array([0.0, 10.0]), np.array([10.0, 0.0])
    pump = Pump(heads, flows, units=3, intake_m=101.0, discharge_elevation_m=110.0, on_m=104.0, off_m=102.0,
                head_loss_m=0.5)
    on = flows_at((pump,), np.array([105.5]), (np.nan, np.nan), 100.0, np.ones((1, 1)))
    off = flows_at((pump,), np.array([105.5]), (np.nan, np.nan), 100.0, np.zeros((1, 1)))
    assert on[0, 0] == pytest.approx(3 * 10.0 * (1 - 5.0 / 10.0), rel=HAND_TOLERANCE) and off[0, 0] == 0.0
    with pytest.raises(ValueError, match="must rise"):
        Pump(heads, flows, units=1, intake_m=103.0, discharge_elevation_m=110.0, on_m=104.0, off_m=102.0)
    z = np.linspace(100.0, 125.0, 26)
    a = np.full(26, 1.0e5)
    with pytest.raises(ValueError, match="intake"):
        ReservoirOutflowStructures(z, a, (), 100.0, structures=(pump,), tailwater_m=101.5)
    deep = ReservoirOutflowStructures(z, a, (), 100.0, structures=(pump,))
    with pytest.raises(ValueError, match="outside its table"):
        deep.run(np.full(200, 50.0), STEP_MINUTES)  # the pool rises past 110.5 m: a negative head


def test_pump_run_times_are_minutes() -> None:
    routing = reservoir_of("pump_times")
    pump = next(s for s in routing.structures if isinstance(s, Pump))
    assert (pump.run_min, pump.rest_min) == (2000.0, 900.0)
    blank = reservoir_of("pump_cycle")
    assert next(s for s in blank.structures if isinstance(s, Pump)).run_min == 0.0
