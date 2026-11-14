"""Diversions against HEC-HMS 4.12 run headless, and by hand. No project data.

The oracle is W72's cases in ``tests/data/hms_diversions``: W59's metric test project with a Source, a Diversion and two
Sinks per basin, each basin re-saved by HMS itself (so every key is one HMS reads), and HMS's series of each run.
``W72 HMS diversions/README.md`` holds the numbers and the probes.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from wadi2d.hms import load_basin
from wadi2d.hydrology.diversion import (
    ChannelRating,
    ConstantDiversion,
    DiversionLimits,
    InflowDiversion,
    LateralWeirDiversion,
)
from wadi2d.hydrology.from_hms import FlowRecord, PairedColumns, ProjectTables, diversion_from_hms
from wadi2d.hydrology.live_network import plan_routes
from wadi2d.hydrology.model import Basin, Diversion, Junction
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.hydrology.structure_kernel import SUBMERGED_SHARE, SUBMERGENCE

DATA = Path(__file__).resolve().parents[1] / "data" / "hms_diversions"
STEP_MINUTES = 5.0
START = datetime(2000, 1, 31, 12, 0)
EXACT_OF_PEAK = 1.0e-12
"""Closed-form methods: HMS's arithmetic, to round-off."""
SOLVED_OF_PEAK = 1.0e-5
"""Weir and pump: HMS's own solve stops within 3e-4 m3/s on a 114 m3/s peak (``probe_laws.py``)."""
CLOSED_FORM = ["div_table", "div_constant", "div_specified", "div_max_flow", "div_max_volume", "div_not_connected"]


def load_case(case: str) -> dict[str, np.ndarray]:
    with (DATA / f"{case}.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {key: np.array([float(row[key]) for row in rows]) for key in rows[0]}


def _tables() -> ProjectTables:
    raw = json.loads((DATA / "tables.json").read_text(encoding="utf-8"))
    flows = np.array(raw.pop("specified_m3s"))
    times = np.datetime64(START, "s") + np.arange(flows.size) * np.timedelta64(int(STEP_MINUTES * 60), "s")
    paired = {name: PairedColumns(np.array(t["x"]), np.array(t["y"])) for name, t in raw.items()}
    return ProjectTables({}, {}, paired, {"W72 Divert": FlowRecord(times, flows)})


def diversion_of(case: str) -> Diversion:
    return _read(DATA / f"{case}.basin")


def _read(path: Path, start: datetime | None = START) -> Diversion:
    return diversion_from_hms(load_basin(path).diversions["Diversion"], _tables(), start)


def _branches(case: str) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    hms = load_case(case)
    passed, diverted = diversion_of(case).routing.branches(hms["inflow"], STEP_MINUTES)
    return hms, passed, diverted


@pytest.mark.parametrize("case", CLOSED_FORM)
def test_closed_form_methods_are_hms(case: str) -> None:
    hms, passed, diverted = _branches(case)
    peak = hms["inflow"].max()
    assert np.abs(diverted - hms["diverted"]).max() <= EXACT_OF_PEAK * peak
    assert np.abs(passed - hms["passed"]).max() <= EXACT_OF_PEAK * peak


@pytest.mark.parametrize("case", ["div_weir", "div_weir_tw", "div_pump"])
def test_solved_methods_route_as_hms(case: str) -> None:
    hms, passed, diverted = _branches(case)
    peak = hms["diverted"].max()
    assert np.abs(diverted - hms["diverted"]).max() <= SOLVED_OF_PEAK * peak
    assert np.array_equal(passed + diverted, hms["inflow"]) or np.abs(passed + diverted - hms["inflow"]).max() < 1e-12


def _drowned_law(routing: LateralWeirDiversion, passed: np.ndarray, diverted: np.ndarray) -> np.ndarray:
    """The weir's flow at a given passed and diverted flow: the stage from the first, the tailwater from the second."""
    out = np.zeros_like(passed)
    for k, (p, d) in enumerate(zip(passed, diverted, strict=True)):
        stage = routing.channel.stage(p)
        free = routing.free(stage)
        level = routing.tailwater.stage(d)
        if free <= 0.0 or level <= routing.crest_m:
            out[k] = free
            continue
        s = (level - routing.crest_m) / (stage - routing.crest_m)
        out[k] = 0.0 if s >= 1.0 else free * np.interp(s, SUBMERGENCE, SUBMERGED_SHARE)
    return out


def test_drowned_weir_is_hms_where_hms_found_its_root() -> None:
    """W67's submergence table on the tailwater rating at the diverted flow is HMS's drowned lateral weir; on 35 of 577
    steps, at the smallest flows on a steep tailwater rating, HMS's own iteration returns a flow that is not a root of
    its law, 0 on 26 of them where a root of 1 to 2 m3/s exists. Ours is a root at every step."""
    hms, passed, diverted = _branches("div_weir_drowned")
    routing = diversion_of("div_weir_drowned").routing
    assert isinstance(routing, LateralWeirDiversion)
    hms_root = np.abs(_drowned_law(routing, hms["passed"], hms["diverted"]) - hms["diverted"]) <= 2.0e-3
    assert (~hms_root).sum() <= 35
    peak = hms["diverted"].max()
    assert np.abs(diverted - hms["diverted"])[hms_root].max() <= SOLVED_OF_PEAK * peak
    assert np.abs(_drowned_law(routing, passed, diverted) - diverted).max() <= 1.0e-6
    assert (hms["diverted"][~hms_root] == 0.0).sum() == 26
    assert np.abs(diverted - hms["diverted"])[~hms_root].max() < 2.2


def test_pump_station_cycling_against_its_own_draw_is_refused() -> None:
    hms = load_case("div_pump_cycle")
    with pytest.raises(ValueError, match="not identified"):
        diversion_of("div_pump_cycle").routing.branches(hms["inflow"], STEP_MINUTES)


def test_not_connected_water_leaves_the_network() -> None:
    hms = load_case("div_not_connected")
    assert diversion_of("div_not_connected").branch is None
    assert hms["received"].max() == 0.0


def test_limits_by_hand() -> None:
    """Constant 50 capped at the inflow, then at 40 m3/s, then at 6,000 m3 over 60 s steps: 600, 2,400, 2,400 m3,
    the fourth step the last 600 m3 (10 m3/s), nothing after."""
    inflow = np.array([10.0, 80.0, 80.0, 80.0, 5.0])
    limits = DiversionLimits(max_flow_m3s=40.0, max_volume_m3=6000.0)
    passed, diverted = ConstantDiversion(50.0, limits).branches(inflow, 1.0)
    assert diverted.tolist() == [10.0, 40.0, 40.0, 10.0, 0.0]
    assert (passed + diverted == inflow).all()


def test_weir_by_hand() -> None:
    """A rating of 100 m3/s per metre above 100 m, a 10 m weir of C 2 at 101 m: Q = 20 (P/100 - 1)^1.5 with
    P + Q = 300; on paper P = 259.65, Q = 40.35 (P = 260 gives 300.48, P = 259.6 gives 299.93)."""
    weir = LateralWeirDiversion(ChannelRating(np.array([100.0, 110.0]), np.array([0.0, 1000.0])), 101.0, 10.0, 2.0)
    passed, diverted = weir.branches(np.array([0.0, 50.0, 300.0]), 5.0)
    assert diverted[:2].tolist() == [0.0, 0.0]
    assert diverted[2] == pytest.approx(20.0 * (passed[2] / 100.0 - 1.0) ** 1.5, abs=1e-8)
    assert passed[2] == pytest.approx(259.65, abs=0.01)


def test_inflow_above_the_table_raises_as_hms_does() -> None:
    table = InflowDiversion(np.array([0.0, 300.0]), np.array([0.0, 150.0]))
    with pytest.raises(ValueError, match="above the table"):
        table.branches(np.array([0.0, 300.5]), 5.0)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("     Constant Flow: 50\n", "     Constant Flow: 50\n     Pattern Name: Monthly\n", "Pattern Name"),
        ("     Diverter: Constant\n", "     Diverter: Unknown\n", "not supported"),
    ],
)
def test_unread_keys_and_methods_raise_by_name(tmp_path: Path, old: str, new: str, message: str) -> None:
    text = (DATA / "div_constant.basin").read_text(encoding="utf-8").replace(old, new)
    path = tmp_path / "case.basin"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        _read(path)


def test_pump_station_run_time_raises(tmp_path: Path) -> None:
    text = (DATA / "div_pump.basin").read_text(encoding="utf-8").replace("Minimum Run Time: ", "Minimum Run Time: 30")
    path = tmp_path / "case.basin"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="run or rest time"):
        _read(path)


def test_specified_flow_needs_a_start_date() -> None:
    with pytest.raises(ValueError, match="start date"):
        _read(DATA / "div_specified.basin", None)


def test_diverted_flow_reaches_its_element_through_the_network() -> None:
    """The network carries the diverted flow to Divert To, as HMS's Sink received it."""
    hms = load_case("div_weir")
    routing = diversion_of("div_weir").routing
    basin = Basin("w72", [
        Junction("Inflow", "Diversion"),
        Diversion("Diversion", "Outlet", routing, branch="Diverted"),
        Junction("Outlet", None),
        Junction("Diverted", None),
    ])
    from wadi2d.hydrology.model import TimeGrid

    run = LumpedEngine(basin).run(None, TimeGrid(STEP_MINUTES, hms["inflow"].size - 1), external={"Inflow": hms["inflow"]})
    assert np.abs(run.outflow["Diverted"] - hms["received"]).max() <= SOLVED_OF_PEAK * hms["received"].max()
    assert np.abs(run.outflow["Outlet"] + run.outflow["Diverted"] - hms["inflow"]).max() < 1e-9


def test_specified_flow_on_a_hand_back_route_is_refused() -> None:
    routing = diversion_of("div_specified").routing
    basin = Basin("w72", [Diversion("Diversion", "Outlet", routing, branch=None), Junction("Outlet", None)])
    with pytest.raises(ValueError, match="gage record ends"):
        plan_routes(basin, ["Diversion"], [])
