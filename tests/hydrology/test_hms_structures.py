"""Reservoir outflow structures against HEC-HMS 4.12 run headless, and by hand. No project data.

The oracle is ``tests/data/hms_structures``: W59's test basins (one Source, one reservoir, one Sink each, written from
scratch, re-saved by HMS itself so every key is one HMS reads) and HMS's own series of each run as CSV. Each
reservoir is built by the reader from HMS's basin file and routes HMS's inflow of record (FLOW-COMBINE); outflow,
pool level, storage, each structure's flow and the evaporation are compared step by step. ``W59 HMS reservoir
structures/README.md`` holds the numbers and how the data were made.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from wadi2d.hms import load_basin
from wadi2d.hms.basin import Reservoir as HmsReservoir
from wadi2d.hydrology.from_hms import PairedColumns, ProjectTables, reservoir_from_hms
from wadi2d.hydrology.reservoir import ReservoirOutflowStructures, Spillway
from wadi2d.hydrology.reservoir_kernel import route_spillways
from wadi2d.hydrology.structures import (
    LevelDamTop,
    MonthlyEvaporation,
    Orifice,
    RatingSpillway,
    TabularSeepage,
    flows_at,
)

DATA = Path(__file__).resolve().parents[1] / "data" / "hms_structures"
START = datetime(2000, 1, 31, 12, 0)
STEP_MINUTES = 5.0
THOUSAND = 1000.0
CASES = [
    "broad", "rating", "orifice", "orifice_tw", "level_dam", "seepage", "seepage_tw", "seepage_in", "storage", "all",
]
EVAPORATION_ONLY = "evaporation"
"""Rating spillway and evaporation alone: HMS's own books do not close there (see its test), so it is apart."""
STRUCTURE_COLUMNS = {
    "orifice_1_m3s": "outlet_1", "dam_top_1_m3s": "damtop_1", "seepage_1_m3s": "seepage",
}
# The floor of the broad-crested path that W55 merged: HMS's adaptive splits past 0.2 m of pool change are not
# identified, and bisecting every part by the same test is within 0.03 % of HMS's peaks (reservoir.py). The broad
# case itself, on the old kernel, parts from HMS by 1.3e-5 of its peak here.
FLOW_TOLERANCE_OF_PEAK = 3.0e-4
LEVEL_TOLERANCE_M = 2.0e-4
STORAGE_TOLERANCE = 3.0e-5
EVAPORATION_TOLERANCE = 1.0e-3
HAND_TOLERANCE = 1.0e-12
LAW_TOLERANCE = 1.0e-9


def load_case(case: str) -> dict[str, np.ndarray]:
    """HMS's series of one case, by column."""
    path = DATA / f"{case}.csv"
    names = path.read_text(encoding="utf-8").splitlines()[0].split(",")
    values = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    return {name: values[:, k] for k, name in enumerate(names)}


def _tables() -> ProjectTables:
    raw = json.loads((DATA / "tables.json").read_text(encoding="utf-8"))
    paired = {}
    for name, table in raw.items():
        scale = THOUSAND if table["y_units"] == "THOU M3" else 1.0
        paired[name] = PairedColumns(np.array(table["x"]), np.array(table["y"]) * scale)
    return ProjectTables({}, {}, paired)


def reservoir_of(case: str) -> ReservoirOutflowStructures:
    """The reservoir the reader builds from the basin file HMS itself saved."""
    basin = load_basin(DATA / f"{case}.basin")
    element = next(e for e in basin.elements if isinstance(e, HmsReservoir))
    routing = reservoir_from_hms(element, _tables(), START).routing
    assert isinstance(routing, ReservoirOutflowStructures)
    return routing


@pytest.fixture(scope="module", params=CASES)
def compared(request: pytest.FixtureRequest):
    case = request.param
    hms = load_case(case)
    return case, hms, reservoir_of(case).run(hms["inflow"], STEP_MINUTES)


def test_outflow_matches_hms(compared) -> None:
    case, hms, run = compared
    peak = np.abs(hms["outflow"]).max()
    assert np.abs(run.main_m3s - hms["outflow"]).max() <= FLOW_TOLERANCE_OF_PEAK * peak, case


def test_pool_and_storage_match_hms(compared) -> None:
    case, hms, run = compared
    assert np.abs(run.pool_m - hms["elevation_m"]).max() <= LEVEL_TOLERANCE_M, case
    assert np.abs(run.storage_m3 - hms["storage_m3"]).max() <= STORAGE_TOLERANCE * hms["storage_m3"].max(), case


def test_each_structure_matches_hms(compared) -> None:
    case, hms, run = compared
    for ours, theirs in STRUCTURE_COLUMNS.items():
        if ours in run.structures_m3s:
            peak = max(np.abs(hms[theirs]).max(), 1.0)
            assert np.abs(run.structures_m3s[ours] - hms[theirs]).max() <= FLOW_TOLERANCE_OF_PEAK * peak, (case, ours)


def _evaporated(run) -> np.ndarray:
    return 0.5 * (run.evaporation_m3s[1:] + run.evaporation_m3s[:-1]) * STEP_MINUTES * 60.0


def test_evaporation_volume_matches_hms(compared) -> None:
    _case, hms, run = compared
    if "evaporation_m3" not in hms:
        pytest.skip("no evaporation in this case")
    assert _evaporated(run).sum() == pytest.approx(hms["evaporation_m3"].sum(), rel=EVAPORATION_TOLERANCE)


def test_evaporation_alone_hms_books_do_not_close_and_ours_do() -> None:
    """With evaporation and no outflow (the pool below the rating's first flow) HMS loses about 33,000 m3 it books
    nowhere, 0.25 % of the inflow, so its pool lies up to 4 cm under ours; the evaporation it reports matches ours.
    Ours closes over the run within what the adaptive parts leave between step-end trapezoids. In the ``all`` case,
    where an orifice always flows, HMS's books close and it matches ours to 2e-5 of the peak (``CASES``)."""
    hms = load_case(EVAPORATION_ONLY)
    run = reservoir_of(EVAPORATION_ONLY).run(hms["inflow"], STEP_MINUTES)
    dt = STEP_MINUTES * 60.0
    volume = dt * np.trapezoid(hms["inflow"])

    def unbooked(inflow, outflow, storage, evaporated):
        return np.diff(storage) - dt * 0.5 * (inflow[1:] + inflow[:-1] - outflow[1:] - outflow[:-1]) + evaporated

    theirs = unbooked(hms["inflow"], hms["outflow"], hms["storage_m3"], hms["evaporation_m3"][1:]).sum()
    ours = unbooked(hms["inflow"], run.main_m3s, run.storage_m3, _evaporated(run)).sum()
    assert theirs < -2.0e-3 * volume
    assert abs(ours) < 1.0e-4 * volume
    assert _evaporated(run).sum() == pytest.approx(hms["evaporation_m3"].sum(), rel=EVAPORATION_TOLERANCE)


def test_structure_laws_on_hms_own_levels() -> None:
    """Each law at HMS's own pool levels gives HMS's own flow to round-off: the law, apart from the routing."""
    # index: the structure's place in (broad-crested spillways, then the others), as the case's basin lists them
    for case, column, index in (("orifice_tw", "outlet_1", 1), ("level_dam", "damtop_1", 1),
                                ("seepage_in", "seepage", 1), ("rating", "spill_1", 0), ("all", "outlet_1", 0)):
        hms = load_case(case)
        routing = reservoir_of(case)
        structures = (*routing.spillways, *routing.structures)
        stage = np.nan if routing.tailwater_m is None else routing.tailwater_m
        flows = flows_at(structures, hms["elevation_m"], (stage, np.nan), float(routing.elevations_m[0]))
        assert np.abs(flows[:, index] - hms[column]).max() <= 1.0e-9 * max(np.abs(hms[column]).max(), 1.0), case


def test_broad_crested_alone_routes_to_the_same_bits_on_both_kernels() -> None:
    """The structure kernel reproduces route_spillways exactly, so a W55 reservoir moves by nothing."""
    hms = load_case("broad")
    plain = reservoir_of("broad")
    assert not plain.structures and plain.tailwater_m is None
    old_main, old_auxiliary = plain.branches(hms["inflow"], STEP_MINUTES)
    new = plain.run(hms["inflow"], STEP_MINUTES)
    assert np.array_equal(old_main, new.main_m3s) and np.array_equal(old_auxiliary, new.auxiliary_m3s)
    two = ReservoirOutflowStructures(
        plain.elevations_m, plain.areas_m2,
        (Spillway(108.0, 60.0, 1.6), Spillway(109.0, 30.0, 1.5, outlet=1)), 103.0,
    )
    main, auxiliary, _ = route_spillways(
        hms["inflow"], 300.0, two.elevations_m, two.storage_m3, np.array([108.0, 109.0]), np.array([60.0, 30.0]),
        np.array([1.6, 1.5]), np.array([0, 1], dtype=np.int64), 103.0, 80, 1.0e-12, 0.1, 8,
    )
    run = two.run(hms["inflow"], STEP_MINUTES)
    assert np.array_equal(main, run.main_m3s) and np.array_equal(auxiliary, run.auxiliary_m3s)


def test_hand_numbers_for_each_law() -> None:
    g = 9.80665
    structures = (
        Orifice(101.0, 1.5, 0.6, barrels=2),
        LevelDamTop(109.5, 150.0, 1.7),
        RatingSpillway(np.array([100.0, 106.0, 107.0]), np.array([0.0, 0.0, 5.0])),
        TabularSeepage(np.array([0.0, 5.0, 10.0]), np.array([0.0, 0.5, 1.5])),
    )
    flows = flows_at(structures, np.array([106.5]), (np.nan, np.nan), 100.0)[0]
    assert flows[0] == pytest.approx(2 * 0.6 * 1.5 * np.sqrt(2 * g * 5.5), rel=HAND_TOLERANCE)
    assert flows[1] == 0.0
    assert flows[2] == pytest.approx(2.5, rel=HAND_TOLERANCE)
    assert flows[3] == pytest.approx(0.5 + 1.5 * 0.2, rel=HAND_TOLERANCE)  # head 6.5 over the table's bottom, 100 m
    over = flows_at(structures, np.array([110.5]), (104.0, np.nan), 100.0)[0]
    assert over[0] == pytest.approx(2 * 0.6 * 1.5 * np.sqrt(2 * g * 6.5), rel=HAND_TOLERANCE)  # head over tailwater
    assert over[1] == pytest.approx(1.7 * 150.0 * 1.0**1.5, rel=HAND_TOLERANCE)
    assert over[3] == pytest.approx(0.5 + 1.5 * 0.2, rel=HAND_TOLERANCE)  # head 6.5 over the tailwater
    below = flows_at(structures, np.array([102.0]), (104.0, np.nan), 100.0)[0]
    assert below[0] == 0.0 and below[3] == pytest.approx(-0.2, rel=HAND_TOLERANCE)  # negative seepage, as HMS


def test_evaporation_rates_by_month_with_hms_february() -> None:
    evaporation = MonthlyEvaporation((310.0, 280.0) + (0.0,) * 10)
    rates = evaporation.rates(datetime(2000, 1, 31, 23, 50), 4, 5.0)
    january, february = 0.31 / (31 * 86400.0), 0.28 / (28 * 86400.0)  # 2000 is a leap year; HMS uses 28 days
    assert rates == pytest.approx([january, january, february, february], rel=HAND_TOLERANCE)


def test_network_series_carry_pool_storage_and_each_structure() -> None:
    """The columns a run writes beside a reservoir's flows (``series/network_<name>.csv``)."""
    from wadi2d.engine.network_series import reservoir_columns
    from wadi2d.hydrology import Reservoir

    hms = load_case("all")
    element = Reservoir(name="Reservoir", downstream=None, routing=reservoir_of("all"))
    columns = reservoir_columns(element, hms["inflow"], hms["outflow"], STEP_MINUTES)
    assert set(columns) == {"pool_m", "storage_m3", "evaporation_m3s", "orifice_1_m3s", "rating_spillway_1_m3s",
                            "dam_top_1_m3s", "seepage_1_m3s"}
    assert np.abs(columns["pool_m"] - hms["elevation_m"]).max() <= LEVEL_TOLERANCE_M
    total = columns["orifice_1_m3s"] + columns["rating_spillway_1_m3s"] + columns["dam_top_1_m3s"]
    assert total + columns["seepage_1_m3s"] == pytest.approx(element.routing.run(hms["inflow"], STEP_MINUTES).main_m3s)


def test_a_job_dates_monthly_evaporation_from_storm_rain_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The job calendar: ``storm.rain_start`` reaches the HMS reader, so a reservoir with monthly evaporation routes
    in a job as in HMS; with no date it refuses in words that name the field. The engine has no Source element
    (W58), so the test basin's Source, HMS's inflow, is cut from a copy."""
    import re
    from types import SimpleNamespace

    import wadi2d.run as run

    text = (DATA / f"{EVAPORATION_ONLY}.basin").read_text(encoding="utf-8")
    basin_file = tmp_path / "evaporation.basin"
    basin_file.write_text(re.sub(r"\nSource: .*?\nEnd:\n", "\n", text, flags=re.S), encoding="utf-8")
    monkeypatch.setattr(run, "_project_tables", lambda _h, _basin: _tables())
    hydrology = SimpleNamespace(basin_json=None, hms_basin=str(basin_file), reach_routing="hms")
    dated = SimpleNamespace(hydrology=hydrology, storm=SimpleNamespace(rain_start="2000-01-31T12:00"), dam_levels=[])
    assert run.run_calendar(dated) == START
    basin, _hms, _cut = run._lumped_basin(dated, "")
    hms = load_case(EVAPORATION_ONLY)
    ours = basin.elements["Reservoir"].routing.run(hms["inflow"], STEP_MINUTES)
    assert _evaporated(ours).sum() == pytest.approx(hms["evaporation_m3"].sum(), rel=EVAPORATION_TOLERANCE)
    undated = SimpleNamespace(hydrology=hydrology, storm=SimpleNamespace(rain_start=None), dam_levels=[])
    basin, _hms, _cut = run._lumped_basin(undated, "")
    with pytest.raises(ValueError, match=r"storm.rain_start"):
        basin.elements["Reservoir"].routing.run(hms["inflow"], STEP_MINUTES)


def test_refusals() -> None:
    z = np.linspace(100.0, 110.0, 11)
    a = np.full(11, 1.0e5)
    with pytest.raises(ValueError, match="rating table ends"):
        ReservoirOutflowStructures(z, a, (), 100.0, structures=(RatingSpillway(z[:5], np.arange(5.0)),))
    with pytest.raises(ValueError, match="start date"):
        ReservoirOutflowStructures(
            z, a, (Spillway(108.0, 10.0, 1.6),), 100.0, evaporation=MonthlyEvaporation((100.0,) * 12)
        ).run(np.full(5, 1.0), STEP_MINUTES)
    with pytest.raises(ValueError, match="elevation-area table"):
        ReservoirOutflowStructures(
            z, None, (Spillway(108.0, 10.0, 1.6),), 100.0, storages_m3=np.cumsum(a) - a[0],
            evaporation=MonthlyEvaporation((100.0,) * 12),
        )
