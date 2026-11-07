"""A generated basin through ``run_job``: the proof of D6b on the synthetic valley, whose answers are known by hand.

The valley (``tests/basin/conftest.py``): two arms join at a fork J2, one reach R1 runs from the fork to the outlet J1 at
the south edge, every pixel drains to J1. Three subbasins: the two arms and the valley below the fork. CN 85 everywhere,
60 mm in an hour, so the excess is 27.17 mm by the SCS formula by hand, on every cell and in every lumped twin alike.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tests.basin.conftest import NX, NY, PIXEL, X0, Y0, valley_dem, write_job, write_raster
from wadi2d.basin.build import build_basin
from wadi2d.basin.contract import read_model, value_of
from wadi2d.config.schema import BasinSettings, RunConfig
from wadi2d.run import EXIT_INVALID, load_job, run_job

pytest.importorskip("whitebox")

SETTINGS = BasinSettings(stream_threshold_km2=0.5, snap_m=30.0, section_half_width_m=300.0, section_search_m=20.0)
SOUTH = Y0 - NY * PIXEL
EXCESS_MM = (60.0 - 0.2 * (25400.0 / 85.0 - 254.0)) ** 2 / (60.0 + 0.8 * (25400.0 / 85.0 - 254.0))
"""SCS: (P - 0.2 S)^2 / (P + 0.8 S), S = 25400 / CN - 254, mm."""
HOURS = 6.0
"""Long enough for the lumped hydrographs to end: the longest NRCS lag here is under an hour."""


@pytest.fixture(scope="module")
def valley(tmp_path_factory) -> dict:
    folder = tmp_path_factory.mktemp("basin_run")
    dem = write_raster(folder / "dem.tif", valley_dem())
    cn = write_raster(folder / "cn.tif", np.full((NY, NX), 85.0))
    job = write_job(folder, dem, terrain={"cn_raster": str(cn), "manning": 0.05})
    basin = build_basin(load_job(job), SETTINGS, None, folder / "basin")["basin"]
    no_reach = build_basin(
        load_job(job), SETTINGS.model_copy(update={"min_reach_m": 5000.0}), None, folder / "no_reach"
    )["basin"]
    model = read_model(basin)
    subbasins = {e["name"]: value_of(e, "area_km2") for e in model["elements"] if e["kind"] == "subbasin"}
    fork = next(e for e in model["elements"] if e["kind"] == "junction" and e["downstream"] is not None)
    outlet = next(e for e in model["elements"] if e["kind"] == "junction" and e["downstream"] is None)
    arms = [e["name"] for e in model["elements"] if e["kind"] == "subbasin" and e["downstream"] == fork["name"]]
    return {
        "folder": folder, "dem": dem, "cn": cn, "basin": Path(basin), "no_reach": Path(no_reach),
        "areas": subbasins, "fork": fork["name"], "arms": arms, "outlet": outlet["name"],
    }  # fmt: skip


def job_on(valley: dict, basin: Path, hours: float = HOURS, **hydrology) -> RunConfig:
    south = [(X0 - 5.0, SOUTH + 2.0), (X0 + NX * PIXEL + 5.0, SOUTH + 2.0)]
    near = [(X0, SOUTH + 4.0 * PIXEL), (X0 + NX * PIXEL, SOUTH + 4.0 * PIXEL)]
    data = {
        "grid": {"dx": PIXEL, "extent": [X0, SOUTH, X0 + NX * PIXEL, Y0]},
        "terrain": {"dem": str(valley["dem"]), "cn_raster": str(valley["cn"]), "manning": 0.05},
        "storm": {"kind": "uniform", "depth_mm": 60.0, "duration_min": 60.0},
        "hydrology": {"basin_json": str(basin), "time_step_min": 2.0, "inject_radius": 12.0, **hydrology},
        "boundaries": [{"kind": "free", "coordinates": south}],
        "outputs": {
            "map_every_s": 0.0, "live_every_s": 0.0, "series_every_s": 30.0, "progress_every_s": 0.5,
            "pixels": {"enabled": False}, "lines": [{"name": "Near outlet", "coordinates": near}],
        },
        "run": {"duration_s": hours * 3600.0, "backend": "cpu", "source_every_s": 30.0, "checkpoint_every_s": 0.0},
    }  # fmt: skip
    return RunConfig.model_validate(data)


def events(out: Path, kind: str) -> list[dict]:
    lines = (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(s) for s in lines if f'"{kind}"' in s[:24]]


def resolved(out: Path) -> dict:
    return json.loads((out / "config.resolved.json").read_text(encoding="utf-8"))["hydrology"]


def excess_m3(valley: dict, names: list[str]) -> float:
    return sum(valley["areas"][n] for n in names) * EXCESS_MM * 1000.0


@pytest.fixture(scope="module")
def lumped(valley: dict) -> tuple:
    out = valley["folder"] / "run_lumped"
    return run_job(job_on(valley, valley["basin"]), out), out


@pytest.fixture(scope="module")
def one_arm_2d(valley: dict) -> tuple:
    out = valley["folder"] / "run_2d"
    cfg = job_on(valley, valley["basin"], subbasins=[{"name": valley["arms"][0], "mode": "2d"}])
    return run_job(cfg, out), out


def test_lumped_by_default_the_grid_gets_no_rain_and_the_water_enters_at_the_outlet(valley: dict, lumped: tuple) -> None:
    run, out = lumped
    assert run.exit_code == 0, run.message
    b = run.balance
    assert b.rain == 0.0
    assert b.inflow == pytest.approx(excess_m3(valley, list(valley["areas"])), rel=2e-3)
    assert abs(b.relative) < 1e-6
    h = resolved(out)
    assert [(s["name"], s["mode"]) for s in h["subbasins"]] == [(n, "lumped") for n in valley["areas"]]
    assert [(i["name"], i["element"]) for i in h["inflows"]] == [(valley["outlet"], valley["outlet"])]
    assert h["handbacks"] == []
    (event,) = events(out, "basin")
    assert event["lumped"] == list(valley["areas"]) and event["two_d"] == [] and event["handbacks"] == []
    routes = {j["junction"]: j for j in event["junctions"]}
    assert routes[valley["outlet"]]["enters_2d"] and routes[valley["fork"]]["route"] == "reach"
    assert not routes[valley["fork"]]["handback"]
    assert events(out, "warn") == []


def test_the_network_series_are_written_for_every_element(valley: dict, lumped: tuple) -> None:
    _run, out = lumped
    model = read_model(valley["basin"])
    written = sorted(p.name for p in (out / "series").glob("network_*.csv"))
    assert written == sorted(f"network_{e['name']}.csv" for e in model["elements"])
    import h5py

    with h5py.File(out / "results.h5", "r") as f:
        outflow = f[f"series/network/{valley['outlet']}/outflow_m3s"][()]
        t = f[f"series/network/{valley['outlet']}/t_s"][()]
    assert float(np.trapezoid(outflow, t)) == pytest.approx(excess_m3(valley, list(valley["areas"])), rel=2e-3)


def test_one_arm_in_2d_gives_the_same_water_and_a_line_at_the_fork_that_closes(valley: dict, lumped: tuple, one_arm_2d: tuple) -> None:
    run, out = one_arm_2d
    assert run.exit_code == 0, run.message
    arm, others = valley["arms"][0], [n for n in valley["areas"] if n != valley["arms"][0]]
    b = run.balance
    assert b.rain == pytest.approx(excess_m3(valley, [arm]), rel=1e-3)
    assert b.lateral == pytest.approx(excess_m3(valley, others), rel=2e-3)
    assert b.rain + b.lateral == pytest.approx(lumped[0].balance.inflow, rel=2e-3)
    assert b.handback > 0.9 * b.rain  # what the arm put on the grid crossed the line, less what is still draining
    assert b.reentry > 0.0
    assert abs(b.relative) < 1e-6
    whole = b.rain + b.lateral - (b.outflow - b.handback) - b.storage - b.network_storage - b.routing_defect
    assert abs(whole) < 1e-6 * (b.rain + b.lateral) + abs(b.routing_defect)
    h = resolved(out)
    (line,) = h["handbacks"]
    assert line["element"] == valley["fork"]
    assert h["inflows"] == [{"name": valley["outlet"], "x": h["inflows"][0]["x"], "y": h["inflows"][0]["y"],
                             "element": valley["outlet"], "entry": "point", "times_s": None, "flows": None}]  # fmt: skip
    (event,) = events(out, "basin")
    fork = next(j for j in event["junctions"] if j["junction"] == valley["fork"])
    assert fork["handback"] and fork["two_d_sources"] == [arm]
    assert (out / "series" / f"handback_{valley['fork']}.csv").is_file()
    assert (out / "series" / "network_R1.csv").is_file()
    assert not (out / "series" / f"network_{arm}.csv").is_file()


def test_an_incomplete_subbasin_is_refused_into_rain_on_grid_with_the_warning_naming_it(valley: dict) -> None:
    model = read_model(valley["basin"])
    first = valley["arms"][1]
    edited = json.loads(json.dumps(model))
    for element in edited["elements"]:
        if element["name"] == first:
            element["parameters"]["curve_number"] = {"value": None, "source": "missing"}
            element["parameters"]["lag_minutes"] = {"value": None, "source": "derived"}
    folder = valley["folder"] / "incomplete"
    folder.mkdir(exist_ok=True)
    (folder / "basin.gpkg").write_bytes((valley["basin"].parent / "basin.gpkg").read_bytes())
    (folder / "basin.json").write_text(json.dumps(edited), encoding="utf-8")
    out = valley["folder"] / "run_incomplete"
    cfg = job_on(valley, folder / "basin.json", hours=1.0, subbasins=[{"name": first, "mode": "lumped"}])
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    warnings = [e["message"] for e in events(out, "warn")]
    assert any(first in w and "curve_number" in w and "not lumped as asked" in w for w in warnings)
    assert run.balance.rain > 0.0
    (event,) = events(out, "basin")
    assert event["two_d"] == [first] and event["incomplete"] == [{"name": first, "missing": ["curve_number"]}]
    assert resolved(out)["subbasins"][[s["name"] for s in resolved(out)["subbasins"]].index(first)]["mode"] == "2d"


def test_an_override_in_the_job_completes_it_and_it_runs_lumped(valley: dict) -> None:
    first = valley["arms"][1]
    folder = valley["folder"] / "incomplete"
    out = valley["folder"] / "run_override"
    cfg = job_on(
        valley, folder / "basin.json", hours=1.0,
        subbasins=[{"name": first, "mode": "lumped", "parameters": {"curve_number": 85.0}}],
    )  # fmt: skip
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    assert run.balance.rain == 0.0
    assert events(out, "warn") == []
    assert events(out, "basin")[0]["two_d"] == []
    subs = resolved(out)["subbasins"]
    assert next(s for s in subs if s["name"] == first)["parameters"] == {"curve_number": 85.0}


def test_two_overlapping_lumped_polygons_stop_the_run_by_name_and_count(valley: dict, tmp_path: Path) -> None:
    """Through the plain polygon route: a generated basin cannot overlap, its polygons are a partition of the pixels."""
    a = [[X0, Y0], [X0 + 1000.0, Y0], [X0 + 1000.0, Y0 - 1000.0], [X0, Y0 - 1000.0], [X0, Y0]]
    b = [[X0 + 500.0, Y0], [X0 + 2000.0, Y0], [X0 + 2000.0, Y0 - 1000.0], [X0 + 500.0, Y0 - 1000.0], [X0 + 500.0, Y0]]
    features = [
        {"type": "Feature", "properties": {"name": name}, "geometry": {"type": "Polygon", "coordinates": [ring]}}
        for name, ring in (("West", a), ("East", b))
    ]
    polygons = tmp_path / "overlap.geojson"
    crs = {"type": "name", "properties": {"name": "EPSG:32640"}}
    polygons.write_text(json.dumps({"type": "FeatureCollection", "crs": crs, "features": features}), encoding="utf-8")
    zeros = {"times_s": [0.0, 3600.0], "flows": [0.0, 0.0], "x": X0 + 100.0, "y": Y0 - 100.0}
    data = job_on(valley, valley["basin"], hours=1.0).model_dump()
    data["hydrology"] = {
        "polygons": str(polygons),
        "subbasins": [{"name": "West", "mode": "lumped"}, {"name": "East", "mode": "lumped"}],
        "inflows": [{"name": "West", **zeros}, {"name": "East", **zeros}],
    }
    run = run_job(RunConfig.model_validate(data), tmp_path / "run")
    assert run.exit_code == EXIT_INVALID
    assert "5000 cells lie under both lumped subbasins West and East (50.00 % of the smaller" in run.message
    data["hydrology"]["subbasins"][1]["mode"] = "2d"
    data["hydrology"]["inflows"].pop()
    run = run_job(RunConfig.model_validate(data), tmp_path / "run2")
    assert run.exit_code == EXIT_INVALID
    assert "5000 cells of 2D subbasin East lie under lumped West" in run.message


def test_a_junction_with_no_reach_feeds_the_grid_and_its_water_reaches_the_next_junction(valley: dict) -> None:
    out = valley["folder"] / "run_no_reach"
    run = run_job(job_on(valley, valley["no_reach"]), out)
    assert run.exit_code == 0, run.message
    model = read_model(valley["no_reach"])
    fork = next(e for e in model["elements"] if e["kind"] == "junction" and e["downstream"] is not None)
    h = resolved(out)
    assert sorted(i["name"] for i in h["inflows"]) == sorted(e["name"] for e in model["elements"] if e["kind"] == "junction")
    assert h["handbacks"] == []
    b = run.balance
    assert b.inflow == pytest.approx(excess_m3(valley, list(valley["areas"])), rel=2e-3)
    assert abs(b.relative) < 1e-6
    import h5py

    with h5py.File(out / "results.h5", "r") as f:
        at_fork = f[f"series/network/{fork['name']}/outflow_m3s"][()]
        below = f[f"series/network/{fork['downstream']}/inflow_m3s"][()]
        t = f["series/lines/Near_outlet/t_s"][()]
        near = np.abs(f["series/lines/Near_outlet/discharge_m3s"][()])
    arms = excess_m3(valley, valley["arms"])
    assert float(np.trapezoid(at_fork, np.arange(at_fork.size) * 120.0)) == pytest.approx(arms, rel=2e-3)
    valley_below = [n for n in valley["areas"] if n not in valley["arms"]]  # drains straight into the outlet
    cut_share = float(np.trapezoid(below, np.arange(below.size) * 120.0))
    assert cut_share == pytest.approx(excess_m3(valley, valley_below), rel=2e-3)  # the fork's water is not in it
    # the line lies 4 cells above the outlet, where the valley subbasin's own inflow enters: what crosses it is the
    # fork's water, run 1.5 km over the ground
    assert float(np.trapezoid(near, t)) == pytest.approx(arms, rel=1e-2)
    (event,) = events(out, "basin")
    plan = next(j for j in event["junctions"] if j["junction"] == fork["downstream"])
    assert plan["two_d_sources"] == [fork["name"]] and plan["enters_2d"]


def test_preflight_and_a_dry_run_take_a_generated_job(valley: dict) -> None:
    from wadi2d.engine.estimate import estimate
    from wadi2d.run import check_inputs, preflight

    cfg = job_on(valley, valley["basin"], subbasins=[{"name": valley["arms"][0], "mode": "2d"}])
    check_inputs(cfg)
    storm, polygons, flows = preflight(cfg, "")
    assert storm is not None and set(polygons) == set(valley["areas"])
    assert [name for name, _p, _t, _q in flows] == [valley["outlet"]]
    assert estimate(cfg, "cpu").cells > 0
