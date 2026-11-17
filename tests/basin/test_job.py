"""A job on a generated basin, resolved: modes, overrides, the inflows and hand-backs the routes give. No 2D run here."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import shapely

from tests.basin.conftest import NX, NY, PIXEL, X0, Y0, valley_dem, write_job, write_raster
from wadi2d.basin import load_network
from wadi2d.basin.build import build_basin
from wadi2d.basin.contract import SOURCE_DERIVED, SOURCE_JOB, read_model, value_of
from wadi2d.basin.geometry import SUBBASINS, geometry_file, model_geometry, read_layer
from wadi2d.basin.job import (
    JUNCTION_SHIFT_CELLS,
    MODE_2D,
    MODE_LUMPED,
    engine_basin,
    generated_basin,
    resolve,
    with_overrides,
)
from wadi2d.config.schema import BasinSettings, RunConfig, Subbasin
from wadi2d.hydrology.model import Junction, Reach
from wadi2d.hydrology.muskingum import Muskingum
from wadi2d.hydrology.routing import MuskingumCunge
from wadi2d.run import load_job

SETTINGS = BasinSettings(stream_threshold_km2=0.5, snap_m=30.0, section_half_width_m=300.0, section_search_m=20.0)
VALLEY_WIDTH_4M = 2.0 * 4.0 / 0.05
"""The V valley is 160 m wide 4 m above its bed (SIDE_SLOPE 0.05)."""


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> dict:
    """The valley's basin: three subbasins, one reach between the fork J2 and the outlet J1."""
    folder = tmp_path_factory.mktemp("valley")
    dem = write_raster(folder / "dem.tif", valley_dem())
    cn = write_raster(folder / "cn.tif", np.full((NY, NX), 85.0))
    job = write_job(folder, dem, terrain={"cn_raster": str(cn), "manning": 0.05})
    written = build_basin(load_job(job), SETTINGS, None, folder / "basin")
    short = build_basin(
        load_job(job), SETTINGS.model_copy(update={"min_reach_m": 5000.0}), None, folder / "no_reach"
    )
    return {"folder": folder, "dem": dem, "cn": cn, "basin": Path(written["basin"]), "no_reach": Path(short["basin"])}


def job_on(generated: dict, basin: Path, **hydrology) -> RunConfig:
    data = {
        "grid": {"dx": PIXEL, "extent": [X0, Y0 - NY * PIXEL, X0 + NX * PIXEL, Y0]},
        "terrain": {"dem": str(generated["dem"]), "cn_raster": str(generated["cn"]), "manning": 0.05},
        "storm": {"kind": "uniform", "depth_mm": 60.0, "duration_min": 60.0},
        "hydrology": {"basin_json": str(basin), **hydrology},
        "run": {"duration_s": 3600.0, "backend": "cpu"},
    }
    return RunConfig.model_validate(data)


def names(model: dict, kind: str) -> list[str]:
    return [e["name"] for e in model["elements"] if e["kind"] == kind]


def test_the_map_reads_back_in_the_jobs_crs_with_exact_polygons(generated: dict) -> None:
    model = read_model(generated["basin"])
    geometry = model_geometry(model, generated["basin"], "EPSG:32640")
    assert set(geometry.subbasins) == set(names(model, "subbasin"))
    assert set(geometry.reaches) == set(names(model, "reach"))
    assert set(geometry.junctions) == set(names(model, "junction"))
    total = sum(g.area for g in geometry.subbasins.values())
    assert total == pytest.approx(NX * NY * PIXEL**2, rel=1e-9)
    for name, polygon in geometry.subbasins.items():
        element = next(e for e in model["elements"] if e["name"] == name)
        assert polygon.area / 1e6 == pytest.approx(value_of(element, "area_km2"), abs=1e-4)
    pairs = [(a, b) for a in geometry.subbasins for b in geometry.subbasins if a < b]
    for a, b in pairs:
        assert geometry.subbasins[a].intersection(geometry.subbasins[b]).area == 0.0
    moved = read_layer(geometry_file(model, generated["basin"]), SUBBASINS, "EPSG:4326")
    assert all(abs(v) < 180.0 for g in moved.values() for v in g.bounds)


def test_lumped_by_default_with_an_inflow_at_the_outlet_and_no_line(generated: dict) -> None:
    cfg = job_on(generated, generated["basin"])
    resolved, gen = resolve(cfg)
    assert set(gen.modes.values()) == {MODE_LUMPED}
    assert gen.notes == []
    assert [i.name for i in gen.inflows] == ["J1"]
    assert gen.inflows[0].element == "J1"
    assert gen.handbacks == []
    assert gen.cut == frozenset()
    assert [s.mode for s in resolved.hydrology.subbasins] == [MODE_LUMPED] * 3
    assert all(s.outlet is None for s in resolved.hydrology.subbasins)
    assert [p.junction for p in gen.junctions] == ["J1", "J2"]
    assert [(p.route, p.enters_2d, p.handback) for p in gen.junctions] == [("none", True, False), ("reach", False, False)]
    assert gen.report()["inflows"] == ["J1"]


def test_a_2d_subbasin_above_the_fork_gets_a_line_square_to_the_reach_and_keeps_the_lumped_water_in_the_network(
    generated: dict,
) -> None:
    model = read_model(generated["basin"])
    fork = next(e for e in model["elements"] if e["kind"] == "junction" and e["downstream"] is not None)
    above = [e["name"] for e in model["elements"] if e["kind"] == "subbasin" and e["downstream"] == fork["name"]]
    cfg = job_on(generated, generated["basin"], subbasins=[{"name": above[0], "mode": "2d"}])
    resolved, gen = resolve(cfg)
    assert gen.modes[above[0]] == MODE_2D
    (line,) = gen.handbacks
    assert line.element == fork["name"]
    plan = next(p for p in gen.junctions if p.junction == fork["name"])
    assert plan.handback and plan.two_d_sources == (above[0],)
    (a, b) = line.coordinates
    x, y = fork["outlet"]
    assert a[1] == pytest.approx(b[1]) and a[1] == pytest.approx(y - JUNCTION_SHIFT_CELLS * PIXEL)
    reach = next(e for e in model["elements"] if e["name"] == "R1")
    width = value_of(reach, "section")["width_m"][-1]
    assert width == pytest.approx(VALLEY_WIDTH_4M, rel=0.1)
    assert abs(b[0] - a[0]) == pytest.approx(cfg.basin.handback_span * width, rel=1e-6)
    assert (a[0] + b[0]) / 2.0 == pytest.approx(x, abs=PIXEL)
    basin = engine_basin(gen.model, gen.modes)
    assert above[0] not in basin.elements
    assert isinstance(basin.elements[fork["name"]], Junction)
    assert isinstance(basin.elements["R1"], Reach)
    two_d = next(s for s in resolved.hydrology.subbasins if s.name == above[0])
    assert two_d.curve_number == 85.0


def test_an_incomplete_subbasin_runs_as_rain_on_grid_and_the_warning_names_what_it_lacks(generated: dict) -> None:
    model = read_model(generated["basin"])
    first = names(model, "subbasin")[0]
    cfg = job_on(generated, generated["basin"], subbasins=[{"name": first, "mode": "lumped"}])
    edited = json.loads(json.dumps(model))
    for element in edited["elements"]:
        if element["name"] == first:
            element["parameters"]["curve_number"] = {"value": None, "source": "missing"}
            element["parameters"]["lag_minutes"] = {"value": None, "source": "derived"}
    path = generated["folder"] / "incomplete.json"
    path.write_text(json.dumps(edited), encoding="utf-8")
    (generated["folder"] / "incomplete.gpkg").write_bytes((generated["folder"] / "basin" / "basin.gpkg").read_bytes())
    edited["geometry_file"] = "incomplete.gpkg"
    path.write_text(json.dumps(edited), encoding="utf-8")
    cfg = cfg.model_copy(update={"hydrology": cfg.hydrology.model_copy(update={"basin_json": str(path)})})
    _resolved, gen = resolve(cfg)
    assert gen.modes[first] == MODE_2D
    assert gen.missing == {first: ["curve_number"]}  # the Kirpich lag needs no CN, so it is derived again
    (note,) = gen.notes
    assert first in note and "curve_number" in note and "rain-on-grid" in note and "not lumped as asked" in note
    assert first not in engine_basin(gen.model, gen.modes).elements


def test_an_override_completes_an_element_without_editing_the_file(generated: dict) -> None:
    model = read_model(generated["basin"])
    first = names(model, "subbasin")[0]
    for element in model["elements"]:
        if element["name"] == first:
            element["parameters"]["curve_number"] = {"value": None, "source": "missing"}
            element["parameters"]["lag_minutes"] = {"value": None, "source": "derived"}
    fixed = with_overrides(model, [Subbasin(name=first, parameters={"curve_number": 80.0})])
    element = next(e for e in fixed["elements"] if e["name"] == first)
    assert element["missing"] == []
    assert element["parameters"]["curve_number"] == {"value": 80.0, "source": SOURCE_JOB}
    assert element["parameters"]["lag_minutes"]["source"] == SOURCE_DERIVED
    assert value_of(element, "lag_minutes") > 0.0


def test_an_override_of_a_lag_input_rederives_a_derived_lag_and_a_given_lag_stays(generated: dict) -> None:
    model = read_model(generated["basin"])
    first, second = names(model, "subbasin")[:2]
    before = {e["name"]: value_of(e, "lag_minutes") for e in model["elements"] if e["kind"] == "subbasin"}
    gentler = 0.5 * value_of(next(e for e in model["elements"] if e["name"] == first), "slope_10_85")
    fixed = with_overrides(
        model,
        [
            Subbasin(name=first, parameters={"slope_10_85": gentler}),
            Subbasin(name=second, parameters={"lag_minutes": 99.0, "curve_number": 60.0}),
        ],
    )
    by_name = {e["name"]: e for e in fixed["elements"]}
    assert value_of(by_name[first], "lag_minutes") > before[first]  # a gentler 10-85 slope lengthens the Kirpich lag
    assert by_name[first]["parameters"]["lag_minutes"]["source"] == SOURCE_DERIVED
    assert value_of(by_name[second], "lag_minutes") == 99.0
    assert by_name[second]["parameters"]["lag_minutes"]["source"] == SOURCE_JOB


def test_a_name_that_is_not_a_subbasin_is_refused(generated: dict) -> None:
    with pytest.raises(ValueError, match="not a subbasin"):
        resolve(job_on(generated, generated["basin"], subbasins=[{"name": "R1", "mode": "2d"}]))
    with pytest.raises(ValueError, match="not a subbasin"):
        resolve(job_on(generated, generated["basin"], subbasins=[{"name": "Nowhere"}]))


def test_a_junction_with_no_reach_sends_its_water_into_the_grid_and_the_link_below_it_is_cut(generated: dict) -> None:
    model = read_model(generated["no_reach"])
    assert names(model, "reach") == []
    cfg = job_on(generated, generated["no_reach"])
    _resolved, gen = resolve(cfg)
    junctions = names(model, "junction")
    assert sorted(i.name for i in gen.inflows) == sorted(junctions)
    fork = next(e for e in model["elements"] if e["kind"] == "junction" and e["downstream"] is not None)
    assert (fork["name"], fork["downstream"]) in gen.cut
    assert gen.handbacks == []
    plan = next(p for p in gen.junctions if p.junction == fork["downstream"])
    assert plan.enters_2d and not plan.handback and plan.two_d_sources == (fork["name"],)


def test_resolving_twice_adds_nothing(generated: dict) -> None:
    model = read_model(generated["basin"])
    above = names(model, "subbasin")[0]
    cfg = job_on(generated, generated["basin"], subbasins=[{"name": above, "mode": "2d"}])
    once, _gen = resolve(cfg)
    twice, _gen = resolve(once)
    assert twice.hydrology == once.hydrology


def test_the_report_is_plain_data(generated: dict) -> None:
    report = generated_basin(job_on(generated, generated["basin"])).report()
    assert json.loads(json.dumps(report)) == report
    assert set(report) == {"junctions", "incomplete", "lumped", "two_d", "inflows", "handbacks"}


def test_the_polygons_mask_exactly_the_cells_of_the_subbasin(generated: dict) -> None:
    from rasterio import features

    model = read_model(generated["basin"])
    geometry = model_geometry(model, generated["basin"])
    transform = __import__("rasterio").transform.from_origin(X0, Y0, PIXEL, PIXEL)
    counted = 0
    for name, polygon in geometry.subbasins.items():
        burned = features.rasterize([(polygon, 1)], out_shape=(NY, NX), transform=transform, fill=0)
        element = next(e for e in model["elements"] if e["name"] == name)
        assert burned.sum() * PIXEL**2 / 1e6 == pytest.approx(value_of(element, "area_km2"), abs=1e-4)
        counted += int(burned.sum())
    assert counted == NX * NY
    assert isinstance(shapely.union_all(list(geometry.subbasins.values())), shapely.Polygon | shapely.MultiPolygon)


# W89: Muskingum on a generated basin


def test_muskingum_routes_a_reach_with_the_jobs_numbers(generated: dict) -> None:
    rows = [{"reach": "R1", "k_hours": 0.3, "x": 0.25, "subreaches": 4}]
    cfg = job_on(generated, generated["basin"], reach_routing="muskingum", muskingum=rows)
    gen = generated_basin(cfg)
    element = next(e for e in gen.model["elements"] if e["name"] == "R1")
    assert element["routing"] == "muskingum" and element["missing"] == []
    assert element["parameters"]["muskingum_k_hours"] == {"value": 0.3, "source": SOURCE_JOB}
    routing = engine_basin(gen.model, gen.modes, cfg.hydrology.reach_routing).elements["R1"].routing
    assert isinstance(routing, Muskingum)
    assert (routing.k_hours, routing.x, routing.subreaches) == (0.3, 0.25, 4)
    assert "R1" not in gen.missing and gen.notes == []
    assert [i.name for i in gen.inflows] == ["J1"]
    assert "routing" not in next(e for e in read_model(generated["basin"])["elements"] if e["name"] == "R1")


def test_muskingum_without_k_and_x_leaves_the_reach_out_and_says_so(generated: dict) -> None:
    """The rule of an incomplete reach: named, cut from the network, its water on the 2D grid."""
    gen = generated_basin(job_on(generated, generated["basin"], reach_routing="muskingum"))
    assert gen.missing["R1"] == ["muskingum_k_hours", "muskingum_x"]
    assert any("reach R1 lacks muskingum_k_hours, muskingum_x" in note for note in gen.notes)
    assert "R1" not in engine_basin(gen.model, gen.modes, "muskingum").elements
    assert sorted(i.name for i in gen.inflows) == ["J1", "J2"]
    routed = generated_basin(job_on(generated, generated["basin"]))
    assert isinstance(engine_basin(routed.model, routed.modes).elements["R1"].routing, MuskingumCunge)


def test_a_reach_of_the_file_is_muskingum_by_its_own_key(generated: dict, tmp_path: Path) -> None:
    """``routing: muskingum`` on a reach of basin.json, under the job's default scheme; a section is then not needed."""
    model = json.loads(generated["basin"].read_text(encoding="utf-8"))
    element = next(e for e in model["elements"] if e["name"] == "R1")
    element["routing"] = "muskingum"
    element["parameters"]["muskingum_k_hours"] = {"value": 0.4, "source": "user"}
    element["parameters"]["muskingum_x"] = {"value": 0.1, "source": "user"}
    element["parameters"]["bottom_width_m"] = {"value": None, "source": "missing"}
    edited = tmp_path / "basin.json"
    edited.write_text(json.dumps(model), encoding="utf-8")
    assert next(e for e in read_model(edited)["elements"] if e["name"] == "R1")["missing"] == []
    routing = load_network(edited).elements["R1"].routing
    assert isinstance(routing, Muskingum) and (routing.k_hours, routing.x, routing.subreaches) == (0.4, 0.1, 1)
    element["parameters"]["muskingum_x"] = {"value": None, "source": "missing"}
    edited.write_text(json.dumps(model), encoding="utf-8")
    assert next(e for e in read_model(edited)["elements"] if e["name"] == "R1")["missing"] == ["muskingum_x"]
    element["routing"] = "kinematic"
    edited.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ValueError, match="routing 'kinematic'"):
        read_model(edited)


def test_a_generated_reach_gets_a_proposal_from_its_section_and_the_file_stays_as_it_was(generated: dict) -> None:
    from wadi2d.engine.muskingum_proposals import propose_reaches

    before = generated["basin"].read_bytes()
    found = propose_reaches(generated["basin"], 5.0)
    (row,) = found["reaches"]
    assert found["kind"] == "generated" and row["name"] == "R1" and row["method"] == "Muskingum Cunge"
    assert row["own"] is None and row["proposal"]["basis"] == "index celerity"
    reach = next(e for e in read_model(generated["basin"])["elements"] if e["name"] == "R1")
    travel_h = value_of(reach, "length_m") / value_of(reach, "index_celerity") / 3600.0
    assert row["proposal"]["k_hours"] == pytest.approx(travel_h, abs=2e-3)
    at_flow = propose_reaches(generated["basin"], 5.0, {"R1": 50.0})["reaches"][0]["proposal"]
    assert at_flow["basis"] == "reference flow" and at_flow["reference_flow_m3s"] == 50.0
    assert generated["basin"].read_bytes() == before
    rows = [{"reach": "R1", **{key: at_flow[key] for key in ("k_hours", "x", "subreaches")}}]
    gen = generated_basin(job_on(generated, generated["basin"], reach_routing="muskingum", muskingum=rows))
    assert gen.notes == [] and "R1" not in gen.missing


def test_muskingum_numbers_for_a_reach_that_is_not_there_are_refused(generated: dict) -> None:
    rows = [{"reach": "R99", "k_hours": 0.3, "x": 0.25}]
    with pytest.raises(ValueError, match=r"names \['R99'\]"):
        generated_basin(job_on(generated, generated["basin"], reach_routing="muskingum", muskingum=rows))


def test_the_jobs_reach_n_stands_for_the_files_and_moves_the_celerity(generated: dict) -> None:
    """W106: hydrology.reach_manning_n on every generated reach, reach_manning on one; the celerity follows."""
    from wadi2d.basin.job import load_model

    plain = load_model(job_on(generated, generated["basin"]).hydrology)
    every = load_model(job_on(generated, generated["basin"], reach_manning_n=0.1).hydrology)
    (reach,) = names(plain, "reach")
    before = next(e for e in plain["elements"] if e["name"] == reach)
    after = next(e for e in every["elements"] if e["name"] == reach)
    assert value_of(before, "manning_n") == pytest.approx(0.05)
    assert after["parameters"]["manning_n"] == {"value": 0.1, "source": SOURCE_JOB}
    assert value_of(after, "index_celerity") < value_of(before, "index_celerity")  # rougher: a slower wave
    one = load_model(job_on(generated, generated["basin"], reach_manning_n=0.1, reach_manning={reach: 0.07}).hydrology)
    assert value_of(next(e for e in one["elements"] if e["name"] == reach), "manning_n") == pytest.approx(0.07)
    with pytest.raises(ValueError, match="not reaches of basin.json"):
        load_model(job_on(generated, generated["basin"], reach_manning={"R99": 0.07}).hydrology)


def test_a_basin_generated_with_the_jobs_reach_n_holds_it(generated: dict) -> None:
    folder = generated["folder"]
    (folder / "n").mkdir(exist_ok=True)
    job = write_job(folder / "n", generated["dem"], terrain={"cn_raster": str(generated["cn"]), "manning": 0.05},
                    hydrology={"reach_manning_n": 0.1})  # fmt: skip
    model = read_model(build_basin(load_job(job), SETTINGS, None, folder / "basin_n")["basin"])
    for reach in (e for e in model["elements"] if e["kind"] == "reach"):
        assert reach["parameters"]["manning_n"] == {"value": 0.1, "source": SOURCE_JOB}


def test_a_job_without_a_reach_n_keeps_its_hash(generated: dict) -> None:
    from wadi2d.run import job_hash

    base = job_on(generated, generated["basin"])
    assert job_hash(base) == job_hash(job_on(generated, generated["basin"], reach_manning={}))
    assert job_hash(base) != job_hash(job_on(generated, generated["basin"], reach_manning_n=0.1))


def _subs(model: dict) -> dict[str, str]:
    return {e["name"]: e["downstream"] for e in model["elements"] if e["kind"] == "subbasin"}


def test_hybrid_2d_on_a_generated_basin_enters_every_lumped_subbasin_at_its_own_outlet(generated: dict) -> None:
    """W106 gap 3: 'outlets' routes no reach and no reservoir; each lumped subbasin at its own outlet, inside its own
    polygon; a subbasin below every last point rains on the grid."""
    model = read_model(generated["basin"])
    every = job_on(generated, generated["basin"], generated_entry="outlets", last_points=["J1"])
    gen = generated_basin(every)
    assert {e["kind"] for e in gen.model["elements"]} == {"subbasin"}
    assert all(down is None for down in _subs(gen.model).values())
    assert gen.inflows == [] and gen.handbacks == [] and gen.cut == frozenset()
    assert set(gen.modes.values()) == {MODE_LUMPED}
    resolved, _gen = resolve(every)
    for sub in resolved.hydrology.subbasins:
        element = next(e for e in model["elements"] if e["name"] == sub.name)
        assert sub.outlet == tuple(element["outlet"]) and sub.entry == "wadi"
    fork = job_on(generated, generated["basin"], generated_entry="outlets", last_points=["J2"])
    above = {name for name, down in _subs(model).items() if down == "J2"}
    gen = generated_basin(fork)
    assert {n for n, m in gen.modes.items() if m == MODE_LUMPED} == above
    assert any("below every last point" in note for note in gen.notes)
    assert gen.last_point_of["J2"] == "J2" and all(gen.last_point_of[n] == "J2" for n in above)


def test_hybrid_lumped_on_a_generated_basin_ends_the_network_at_the_last_point(generated: dict) -> None:
    """W106 gap 3: 'last_points' keeps what lies above the last point, routed as in the file, and its outflow enters
    on the edge of the catchments left out; the reach below and the subbasin below are not lumped."""
    model = read_model(generated["basin"])
    fork = job_on(generated, generated["basin"], generated_entry="last_points", last_points=["J2"])
    gen = generated_basin(fork)
    kept = {e["name"] for e in gen.model["elements"] if e["kind"] != "subbasin"}
    assert kept == {"J2"}
    (inflow,) = gen.inflows
    assert inflow.element == "J2" and inflow.entry == "edge" and gen.handbacks == []
    above = {name for name, down in _subs(model).items() if down == "J2"}
    assert {n for n, m in gen.modes.items() if m == MODE_LUMPED} == above
    plain = generated_basin(job_on(generated, generated["basin"]))
    assert {i.element for i in plain.inflows} != {"J2"} or plain.handbacks  # the file's own routes, as always


def test_a_hybrid_rule_names_a_last_point_the_file_does_not_hold(generated: dict) -> None:
    with pytest.raises(ValueError, match="does not hold"):
        generated_basin(job_on(generated, generated["basin"], generated_entry="outlets", last_points=["J99"]))
    with pytest.raises(ValueError, match="for a generated basin"):
        RunConfig.model_validate(
            {"terrain": {"dem": "x.tif"}, "hydrology": {"hms_basin": "a.basin", "generated_entry": "outlets"}}
        )


def test_hybrid_2d_reads_a_lumped_curve_at_the_last_points_area(generated: dict) -> None:
    """W106: the subbasins above J2 read the curve at J2's drainage area, the file's, one factor per last point."""
    from wadi2d.engine.entry_area import read_areas
    from wadi2d.run import _area_basin, _entry_map, _last_point_map, _lumped_basin

    model = read_model(generated["basin"])
    cfg = job_on(generated, generated["basin"], generated_entry="outlets", last_points=["J2"])
    cfg = resolve(cfg)[0]
    basin, _hms, decided = _lumped_basin(cfg, "")
    read = read_areas(_area_basin(basin), _entry_map(cfg, basin, decided), _last_point_map(cfg, basin))
    j2 = next(e for e in model["elements"] if e["name"] == "J2")
    for name, (area, at, why) in read.items():
        assert at == "J2" and why == "last point" and area == pytest.approx(value_of(j2, "drainage_area_km2"))
