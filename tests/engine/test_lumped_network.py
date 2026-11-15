"""Lumped water kept on the HMS network down to the grid, and the lumped-only run (W88).

The valley of :mod:`tests.engine.test_left_out` with an HMS basin of its own: ``Up`` (west, lumped) drains to junction
``J1``, a lag reach ``R1`` carries it to ``J2``, where ``Low`` (east) joins, and ``J2`` drains to the sink ``Out``.
"""

from __future__ import annotations

import json

import h5py
import numpy as np
import pytest
from pydantic import ValidationError

from tests.engine.test_handback import HEAD, SUB
from tests.engine.test_left_out import BELOW, DX, EDGE, MID, NX, SOUTH, X0, Y0, events, ring, valley_job
from wadi2d.config.schema import RunConfig
from wadi2d.engine.lumped_run import MARKER
from wadi2d.engine.network_layers import FILE as NETWORK_FILE
from wadi2d.run import InvalidJob, _resolved, carried_subbasins, job_hash, left_out_of, run_job

LOW_AREA = 0.2
TABLE = {"areas_km2": [0.01, 100.0], "factors": [1.0, 0.5], "table_type": "test table"}


def sub(name: str, down: str, area: float = 0.1, x: float = 0.0, y: float = 0.0) -> str:
    text = SUB.replace("Subbasin: Side", f"Subbasin: {name}").replace("Area: 0.1", f"Area: {area:g}").format(down=down)
    return text.replace("End:", f"     Canvas X: {x}\n     Canvas Y: {y}\nEnd:", 1)


def element(kind: str, name: str, down: str | None, x: float, y: float, extra: str = "") -> str:
    below = f"     Downstream: {down}\n" if down else ""
    return f"{kind}: {name}\n{below}     Canvas X: {x}\n     Canvas Y: {y}\n{extra}End:\n\n"


def basin(tmp_path):
    path = tmp_path / "net.basin"
    path.write_text(
        HEAD
        + sub("Up", "J1", 0.1, X0 + 80.0, MID)
        + element("Junction", "J1", "R1", EDGE - 20.0, MID)
        + element("Reach", "R1", "J2", BELOW[0], BELOW[1], "\n     Route: Lag\n     Lag: 10\n")
        + sub("Low", "J2", LOW_AREA, X0 + 300.0, MID + 20.0)
        + element("Junction", "J2", "Out", X0 + 300.0, MID)
        + element("Sink", "Out", None, X0 + 380.0, MID),
        encoding="utf-8",
    )
    return path


def polygons(tmp_path):
    shapes = {"Up": ring(X0 - 10.0, EDGE), "Low": ring(EDGE, X0 + NX * DX + 10.0)}
    features = [
        {"type": "Feature", "properties": {"name": n}, "geometry": {"type": "Polygon", "coordinates": [r]}}
        for n, r in shapes.items()
    ]
    path = tmp_path / "net.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


def net_job(tmp_path, low: str = "2d", entry: str = "network", exclude: bool = False, **parts) -> RunConfig:
    subbasins = [{"name": "Up", "mode": "lumped", "outlet": (X0 + 150.0, MID)}, {"name": "Low", "mode": low}]
    if low == "lumped":
        subbasins[1]["outlet"] = (X0 + 300.0, MID)
    hydrology = {
        "hms_basin": str(basin(tmp_path)), "polygons": str(polygons(tmp_path)), "inflows": [], "subbasins": subbasins,
        "lumped_entry": entry, **parts.pop("hydrology", {}),
    }  # fmt: skip
    return valley_job(tmp_path, exclude, hydrology=hydrology, **parts)


def test_the_lumped_water_stays_on_the_reach_and_enters_where_rain_on_grid_joins(tmp_path) -> None:
    cfg, _gen = _resolved(net_job(tmp_path), "")
    (inflow,) = cfg.hydrology.inflows
    assert (inflow.name, inflow.element, (inflow.x, inflow.y), inflow.enters) == ("R1 outflow", "R1", BELOW, True)
    assert [s.outlet for s in cfg.hydrology.subbasins if s.name == "Up"] == [None]
    assert _resolved(cfg, "")[0] == cfg, "resolving a resolved job adds nothing"
    assert carried_subbasins(cfg) == {"Up": "R1 outflow"}
    assert _resolved(net_job(tmp_path, entry="outlet"), "")[0] == net_job(tmp_path, entry="outlet")


def test_the_run_equals_the_same_inflow_given_by_hand_and_the_exclude_tick_is_real(tmp_path) -> None:
    by_rule = run_job(net_job(tmp_path), tmp_path / "rule")
    hand = {"inflows": [{"name": "R1 outflow", "x": BELOW[0], "y": BELOW[1], "element": "R1"}]}
    subs = {"subbasins": [{"name": "Up", "mode": "lumped"}, {"name": "Low", "mode": "2d"}]}
    by_hand = run_job(net_job(tmp_path, entry="outlet", hydrology={**hand, **subs}), tmp_path / "hand")
    assert by_rule.exit_code == 0 and by_hand.exit_code == 0, (by_rule.message, by_hand.message)
    assert by_rule.balance.inflow == by_hand.balance.inflow and by_rule.balance.outflow == by_hand.balance.outflow
    assert left_out_of(net_job(tmp_path, exclude=True)).names == ("Up",)
    cut = run_job(net_job(tmp_path, exclude=True), tmp_path / "cut")
    assert cut.exit_code == 0 and cut.balance.outflow == pytest.approx(by_rule.balance.outflow, rel=1e-5)
    import fiona

    with fiona.open(tmp_path / "cut" / NETWORK_FILE, layer="subbasins") as src:
        (row,) = [f["properties"] for f in src]
    assert row["name"] == "Up" and row["left_out"] == 1 and row["enters_at"] == "R1 outflow"
    assert "left out of the 2D mesh" in row["label"] and row["peak_m3s"] > 0.0


def test_an_icon_missing_and_a_generated_basin_are_refused(tmp_path) -> None:
    data = net_job(tmp_path).model_dump(mode="json")
    path = tmp_path / "net.basin"
    path.write_text(path.read_text(encoding="utf-8").replace(f"     Canvas X: {BELOW[0]}\n     Canvas Y: {BELOW[1]}\n", ""), encoding="utf-8")
    with pytest.raises(InvalidJob, match="no icon"):
        _resolved(RunConfig.model_validate(data), "")
    with pytest.raises(ValidationError, match="generated basin"):
        RunConfig.model_validate({"hydrology": {"basin_json": "b.json", "lumped_entry": "network"}})


def test_all_lumped_leaves_at_the_sink_and_a_domain_wholly_left_out_runs_the_hms_way(tmp_path) -> None:
    cfg, _gen = _resolved(net_job(tmp_path, low="lumped"), "")
    (inflow,) = cfg.hydrology.inflows
    assert (inflow.element, inflow.enters) == ("Out", False)
    assert carried_subbasins(cfg) == {"Up": "Out outflow", "Low": "Out outflow"}
    out = tmp_path / "hms_way"
    run = run_job(net_job(tmp_path, low="lumped", exclude=True), out)
    assert run.exit_code == 0 and run.status == "finished", run.message
    assert run.backend == "lumped" and run.products == "none"
    said = [e for e in events(out) if e.get("ev") == "warn"]
    assert any("the lumped network alone" in e["message"] for e in said)
    resolved = json.loads((out / "config.resolved.json").read_text(encoding="utf-8"))
    assert resolved["run"]["lumped_only"] is True
    marker = json.loads((out / MARKER).read_text(encoding="utf-8"))
    assert marker["kind"] == "lumped" and marker["elements"] == 6
    with h5py.File(out / "results.h5", "r") as f:
        assert bool(f.attrs["lumped_only"]) and "mask" not in f and "maps" not in f
        names = sorted(str(g.attrs["name"]) for g in f["series/network"].values())
    assert names == ["J1", "J2", "Low", "Out", "R1", "Up"]
    assert (out / "series" / "network_Out.csv").is_file()
    done = [e for e in events(out) if e.get("ev") == "done"][-1]
    assert done["status"] == "finished" and done["lumped_only"] is True


def test_a_lumped_only_run_writes_every_element_and_the_dock_reads_it(tmp_path) -> None:
    from wadi2d.products.result_lines import catalogue

    cfg = net_job(tmp_path, low="lumped", entry="outlet", run={"lumped_only": True, "duration_s": 3600.0})
    out = tmp_path / "lumped"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    listing = catalogue(out)
    by_name = {item["name"]: item for item in listing["lumped"]}
    assert set(by_name) == {"J1", "J2", "Low", "Out", "R1", "Up"} and listing["frames_s"] == []
    j2 = np.asarray(by_name["J2"]["outflow_m3s"])
    parts = np.asarray(by_name["R1"]["outflow_m3s"]) + np.asarray(by_name["Low"]["outflow_m3s"])
    assert np.allclose(j2, parts, atol=2e-3), "the junction sums its inflows (the listing rounds to 1e-3)"
    assert "rain_mm" in by_name["Up"]
    import fiona

    layers = fiona.listlayers(out / NETWORK_FILE)
    assert set(layers) == {"subbasins", "points"}
    with fiona.open(out / NETWORK_FILE, layer="points") as src:
        points = {f["properties"]["name"]: f["properties"] for f in src}
    assert set(points) == {"J1", "J2", "Out"} and points["J2"]["outflow_peak_m3s"] == pytest.approx(j2.max(), abs=1e-3)
    assert "m3/s at" in points["J2"]["label"]


def test_the_lumped_only_run_refuses_rain_on_grid_and_hand_backs(tmp_path) -> None:
    run = run_job(net_job(tmp_path, run={"lumped_only": True}), tmp_path / "refused")
    assert run.exit_code == 2 and "rain-on-grid" in run.message and "Low" in run.message


def test_each_element_reads_its_own_area_as_hms_depth_area_analysis(tmp_path) -> None:
    storm = {"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0, "arf": TABLE, "storm_area_km2": 50.0}
    lumped = {"lumped_only": True, "duration_s": 3600.0}

    def run_at(name: str, **hydro):
        cfg = net_job(tmp_path, low="lumped", entry="outlet", storm=storm, run=lumped, hydrology=hydro)
        assert run_job(cfg, tmp_path / name).exit_code == 0
        return {g.attrs["name"]: g["outflow_m3s"][:] for g in h5py.File(tmp_path / name / "results.h5", "r")["series/network"].values()}

    each = run_at("each", arf_by_element=True)
    for element, area in (("Up", 0.1), ("J2", 0.1 + LOW_AREA), ("Low", LOW_AREA)):
        at = dict(storm, storm_area_km2=area)
        cfg = net_job(tmp_path, low="lumped", entry="outlet", storm=at, run=lumped)
        assert run_job(cfg, tmp_path / f"at_{element}").exit_code == 0
        with h5py.File(tmp_path / f"at_{element}" / "results.h5", "r") as f:
            plain = {g.attrs["name"]: g["outflow_m3s"][:] for g in f["series/network"].values()}
        assert np.allclose(each[element], plain[element], rtol=1e-12, atol=0.0), element
    whole = run_at("whole")
    assert each["Up"].max() > whole["Up"].max(), "0.1 km2 reads less reduction than the storm's 50 km2"
    marker = json.loads((tmp_path / "each" / MARKER).read_text(encoding="utf-8"))
    j2 = next(row for row in marker["peaks"] if row["element"] == "J2")
    assert j2["storm_area_km2"] == pytest.approx(0.3) and 0.5 < j2["arf"] < 1.0
    with pytest.raises(ValidationError, match=r"storm.arf"):
        net_job(tmp_path, low="lumped", hydrology={"arf_by_element": True})
    two_d = net_job(tmp_path, storm=storm, hydrology={"arf_by_element": True})
    assert run_job(two_d, tmp_path / "two_d").exit_code == 2


def test_old_jobs_keep_their_hash(tmp_path) -> None:
    cfg = net_job(tmp_path, entry="outlet")
    data = cfg.model_dump(mode="json")
    data["hydrology"].pop("lumped_entry")
    data["hydrology"].pop("arf_by_element")
    data["run"].pop("lumped_only")
    assert job_hash(RunConfig.model_validate(data)) == job_hash(cfg)
    flagged = cfg.model_dump(mode="json")
    flagged["hydrology"]["inflows"] = [{"name": "I", "x": X0, "y": Y0, "element": "R1"}]
    explicit = json.loads(json.dumps(flagged))
    explicit["hydrology"]["inflows"][0]["enters"] = True
    assert job_hash(RunConfig.model_validate(flagged)) == job_hash(RunConfig.model_validate(explicit))
    assert SOUTH < MID
