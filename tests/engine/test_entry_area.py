"""W98: a lumped curve in a run with a 2D part reads each lumped subbasin at the total upstream area of the element where
its water enters the grid (his rule of 2026-11-15), and an element above its entry is reported from a lumped rerun at
its own drainage area.

The network, areas in km2, every subbasin CN 100 with no initial abstraction, so the excess is the reduced rain:

    A 0.01 -> J <- B 0.02            J enters the grid (inflow "J in")       J: 0.03
    J -> RJ -> Out
    C 0.03 -> D1 -> Rd -> D2 <- E 0.04   D2 enters the grid (inflow "D2 in")   D1, Rd: 0.03; D2: 0.07
    D2 -> Out

The curve falls linearly from 1 at 0 km2 to 0.5 at 0.1 km2, so the factor is 1 - 5 x area: 0.85 at J's 0.03 km2 and 0.65
at D2's 0.07 km2, 0.95, 0.90 and 0.80 at the subbasins' own 0.01, 0.02 and 0.04 km2, by hand.
"""

from __future__ import annotations

import json

import h5py
import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job
from tests.engine.test_handback import DX, HEAD, MIDDLE, NX, NY, SUB, plane
from wadi2d.engine.entry_area import ENTRY_AREA_KIND, ENTRY_AREAS_FILE
from wadi2d.hydrology.from_hms import PairedColumns, ProjectTables
from wadi2d.run import _lumped_basin, _lumped_rain, _network, job_hash, run_job

CURVE = {"areas_km2": [0.0, 0.1], "factors": [1.0, 0.5], "table_type": "test curve"}
DEPTH_MM = 50.0
FACTOR = {"J": 0.85, "D2": 0.65, "A": 0.95, "B": 0.90, "C": 0.85, "E": 0.80, "D1": 0.85, "Rd": 0.85}
"""1 - 5 x area, by hand, at each element's own drainage area."""
ENTERS = {"A": "J", "B": "J", "C": "D2", "E": "D2"}
POOL = "     Route: Modified Puls\n     Routing Curve: Elevation-Area-Outflow\n     Initial Elevation: 100\n" \
       "     Elevation-Area Table: EA\n     Elevation-Outflow Table: EQ\n     Primary Table: Elevation-Area\n"  # fmt: skip
LAG = "\n     Route: Lag\n     Lag: 10\n"
DURATION_S = 4 * 3600.0
M3_PER_KM2_MM = 1000.0


def _sub(name: str, down: str, area: float) -> str:
    return SUB.replace("Subbasin: Side", f"Subbasin: {name}").replace("Area: 0.1", f"Area: {area:g}").format(down=down)


def _element(kind: str, name: str, down: str | None, extra: str = "") -> str:
    below = f"     Downstream: {down}\n" if down else ""
    return f"{kind}: {name}\n{below}{extra}End:\n\n"


def _basin(tmp_path):
    path = tmp_path / "entry.basin"
    path.write_text(
        HEAD + _sub("A", "J", 0.01) + _sub("B", "J", 0.02) + _element("Junction", "J", "RJ")
        + _element("Reach", "RJ", "Out", LAG)
        + _sub("C", "D1", 0.03) + _element("Reservoir", "D1", "Rd", POOL) + _element("Reach", "Rd", "D2", LAG)
        + _sub("E", "D2", 0.04) + _element("Reservoir", "D2", "Out", POOL) + _element("Sink", "Out", None),
        encoding="utf-8",
    )  # fmt: skip
    return path


def _polygons(tmp_path):
    """The hills, north of the domain: their rain is the network's, none of the grid's."""

    def ring(k: int) -> list:
        x0 = X0 + 50.0 * k
        return [[x0, Y0 + 10.0], [x0 + 40.0, Y0 + 10.0], [x0 + 40.0, Y0 + 50.0], [x0, Y0 + 50.0], [x0, Y0 + 10.0]]

    features = [
        {"type": "Feature", "properties": {"name": name}, "geometry": {"type": "Polygon", "coordinates": [ring(k)]}}
        for k, name in enumerate("ABCE")
    ]
    path = tmp_path / "hills.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


@pytest.fixture
def pools(monkeypatch):
    """Both dams on one table: a sill at 101 m over 1 m2, so 1 m3 of dead storage, then a weir; the tables of a project
    file stand in."""
    levels = np.array([100.0, 101.0, 110.0])
    tables = ProjectTables(
        {}, {}, {"EA": PairedColumns(levels, np.full(3, 1.0)), "EQ": PairedColumns(levels, np.array([0.0, 0.0, 90.0]))}
    )
    monkeypatch.setattr("wadi2d.run._project_tables", lambda _h, _b: tables)


def _job(tmp_path, reduction: dict | None = None, own: dict | None = None, **parts):
    storm = parts.pop("storm", {"kind": "depth", "depth_mm": DEPTH_MM, "duration_min": 60.0})
    if reduction is not None:
        storm["area_reduction"] = reduction
    subbasins = [{"name": n, "mode": "lumped", **({"storm_area_km2": own[n]} if own and n in own else {})} for n in "ABCE"]
    inflows = [
        {"name": "J in", "x": X0 + 100.0, "y": MIDDLE, "element": "J"},
        {"name": "D2 in", "x": X0 + 300.0, "y": MIDDLE, "element": "D2"},
    ]
    hydrology = {"hms_basin": str(_basin(tmp_path)), "time_step_min": 5.0, "subbasins": subbasins, "inflows": inflows,
                 "polygons": str(_polygons(tmp_path))}  # fmt: skip
    run = {"duration_s": DURATION_S, "backend": "cpu", **parts.pop("run", {})}
    return job(plane(tmp_path), NX, NY, DX, storm=storm, hydrology=hydrology, run=run, **parts)


CURVE_SPLIT = {"lumped": {"form": "curve", "table": CURVE}, "grid": {"form": "coefficient", "coefficient": 1.0}}


def _depth(cfg, name: str) -> float:
    basin, hms, _cut = _lumped_basin(cfg, "")
    return float(_lumped_rain(cfg, _storm(cfg), basin, hms, "").over(name).increments(5.0, 24).sum())


def _storm(cfg):
    from wadi2d.forcing import build_storm

    return build_storm(cfg)


def _volume(flow: np.ndarray, dt_s: float = 300.0) -> float:
    return float(np.trapezoid(flow)) * dt_s


def test_each_subbasin_reads_the_curve_at_its_entry_element_s_area(tmp_path, pools) -> None:
    cfg = _job(tmp_path, CURVE_SPLIT)
    for name, entry in ENTERS.items():
        assert _depth(cfg, name) == pytest.approx(DEPTH_MM * FACTOR[entry], rel=1e-12), name
    own = _job(tmp_path, CURVE_SPLIT, own={"E": 0.01})
    assert _depth(own, "E") == pytest.approx(DEPTH_MM * 0.95, rel=1e-12), "a storm area of its own still wins"
    assert _depth(own, "C") == pytest.approx(DEPTH_MM * FACTOR["D2"], rel=1e-12)
    fixed = _job(tmp_path, {"lumped": {"form": "area", "table": CURVE, "area_km2": 0.05}})
    coefficient = _job(tmp_path, {"lumped": {"form": "coefficient", "coefficient": 1.0}})
    for name in ENTERS:
        assert _depth(fixed, name) == pytest.approx(DEPTH_MM * 0.75, rel=1e-12), "a fixed area: one factor"
        assert _depth(coefficient, name) == pytest.approx(DEPTH_MM, rel=1e-12), "a coefficient of 1: no ARF"


def test_the_grid_takes_the_entry_area_hydrograph_and_an_element_above_reads_its_own(tmp_path, pools) -> None:
    cfg = _job(tmp_path, CURVE_SPLIT)
    table, _live, series = _network(cfg, _storm(cfg))
    entering = {name: q for name, _point, _t, q in table}
    # CN 100 and no loss: what each entry passes over the event is its area x its entry factor x the depth
    assert _volume(series.run.inflow["J"]) == pytest.approx(0.03 * FACTOR["J"] * DEPTH_MM * M3_PER_KM2_MM, rel=1e-3)
    assert _volume(series.run.inflow["D2"]) == pytest.approx(0.07 * FACTOR["D2"] * DEPTH_MM * M3_PER_KM2_MM, rel=1e-3)
    assert np.array_equal(entering["D2 in"], series.run.outflow["D2"]) and np.array_equal(entering["J in"], series.run.outflow["J"])
    assert set(series.own_area) == {"A", "B", "C", "E", "D1", "Rd"}, "every element above its entry, not J or D2"
    d1 = series.own_area["D1"]
    assert _volume(d1.inflow["D1"]) == pytest.approx(0.03 * FACTOR["D1"] * DEPTH_MM * M3_PER_KM2_MM, rel=1e-3)
    assert _volume(series.run.inflow["D1"]) == pytest.approx(0.03 * FACTOR["D2"] * DEPTH_MM * M3_PER_KM2_MM, rel=1e-3)
    assert series.columns("D1")["inflow_m3s"] is d1.inflow["D1"]
    record = series.record
    rows = {row["subbasin"]: row for row in record["subbasins"]}
    for name, entry in ENTERS.items():
        assert rows[name]["enters_at"] == entry and rows[name]["factor"] == pytest.approx(FACTOR[entry], abs=1e-6)
    d1_row = next(row for row in record["elements"] if row["element"] == "D1")
    assert (d1_row["enters_at"], d1_row["own_factor"], d1_row["entry_factor"]) == ("D2", 0.85, 0.65)


def test_the_upstream_dam_s_own_area_series_is_the_lumped_only_run_s(tmp_path, pools) -> None:
    """The rerun at D1's own area is what a lumped-only run with the same curve reads at D1 (HMS's depth-area analysis)."""
    cfg = _job(tmp_path, CURVE_SPLIT)
    _table, _live, series = _network(cfg, _storm(cfg))
    alone = _job(tmp_path, {"lumped": {"form": "curve", "table": CURVE}}, run={"lumped_only": True})
    assert run_job(alone, tmp_path / "alone").exit_code == 0
    with h5py.File(tmp_path / "alone" / "results.h5", "r") as f:
        each = {g.attrs["name"]: g["outflow_m3s"][:] for g in f["series/network"].values()}
    for name in ("D1", "Rd", "C", "E", "A"):
        assert np.allclose(series.columns(name)["outflow_m3s"], each[name], rtol=1e-12, atol=0.0), name
    for name in ("J", "D2"):
        assert np.allclose(series.columns(name)["outflow_m3s"], each[name], rtol=1e-12, atol=0.0), name


def test_a_run_writes_both_series_and_says_which_is_of_record(tmp_path, pools) -> None:
    cfg = _job(tmp_path, CURVE_SPLIT, run={"duration_s": 600.0})
    out = tmp_path / "run"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    saved = json.loads((out / ENTRY_AREAS_FILE).read_text(encoding="utf-8"))
    assert {row["element"] for row in saved["elements"]} == {"A", "B", "C", "E", "D1", "Rd"}
    assert (out / "series" / f"{ENTRY_AREA_KIND}_D1.csv").is_file() and (out / "series" / "network_D1.csv").is_file()
    assert not (out / "series" / f"{ENTRY_AREA_KIND}_D2.csv").exists(), "the entry is read at its own area already"
    with h5py.File(out / "results.h5", "r") as f:
        record, grid = f["series/network/D1/inflow_m3s"][:], f[f"series/{ENTRY_AREA_KIND}/D1/inflow_m3s"][:]
    assert record.sum() > grid.sum() > 0.0, "D1 at its own 0.03 km2 reads less reduction than at D2's 0.07"
    lines = [json.loads(line) for line in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    said = [e for e in lines if e.get("kind") == "lumped_entry_areas"]
    assert said and said[0]["subbasins"] == 4


def test_a_generated_basin_finds_its_entries_from_its_own_routes(tmp_path_factory) -> None:
    """The valley of :mod:`tests.engine.test_basin_run`: three lumped subbasins, the arms' water routed down R1, all
    of it entering at the outlet junction; each subbasin reads the curve at the outlet's area, the total."""
    pytest.importorskip("whitebox")
    from tests.engine import test_basin_run
    from wadi2d.run import _entry_map, _resolved

    valley = test_basin_run.valley.__wrapped__(tmp_path_factory)  # the module's fixture, built once here
    job_on = test_basin_run.job_on
    wide = {"areas_km2": [0.0, 100.0], "factors": [1.0, 0.5], "table_type": "test curve"}
    data = job_on(valley, valley["basin"]).model_dump(mode="json")
    data["storm"]["area_reduction"] = {"lumped": {"form": "curve", "table": wide}}
    cfg, _generated = _resolved(type(job_on(valley, valley["basin"])).model_validate(data), "")
    basin, hms, decided = _lumped_basin(cfg, "")
    entry = _entry_map(cfg, basin, decided)
    total = sum(valley["areas"].values())
    assert {entry[name] for name in valley["areas"]} == {valley["outlet"]}
    assert basin.drainage_area(valley["outlet"]) == pytest.approx(total, rel=1e-12)
    rain = _lumped_rain(cfg, _storm(cfg), basin, hms, "", decided)
    for name in valley["areas"]:
        assert float(rain.over(name).increments(2.0, 60).sum()) == pytest.approx(60.0 * (1.0 - 0.005 * total), rel=1e-12)
    _table, _live, series = _network(cfg, _storm(cfg))
    assert set(valley["arms"]) | {valley["fork"]} <= set(series.own_area), "above the outlet: their own areas"
    assert valley["outlet"] not in series.own_area


def test_jobs_without_a_lumped_curve_hash_and_read_as_before(tmp_path, pools) -> None:
    old = _job(tmp_path, own={"C": 0.07, "E": 0.07},
               storm={"kind": "uniform", "depth_mm": DEPTH_MM, "duration_min": 60.0, "arf": CURVE, "storm_area_km2": 0.03})  # fmt: skip
    assert _depth(old, "C") == pytest.approx(DEPTH_MM * 0.65, rel=1e-12) and _depth(old, "A") == pytest.approx(
        DEPTH_MM * 0.85, rel=1e-12
    )  # fmt: skip
    _table, _live, series = _network(old, _storm(old))
    assert series.own_area == {} and series.record is None
    assert job_hash(old) == job_hash(type(old).model_validate(json.loads(old.model_dump_json())))
