"""W105: the lumped model ends at its last points (his rule of 2026-11-16).

"In Lumped and Hybrid Lumped, the ARF applies to each point's upstream area. But in Hybrid 2D, the ARF applies to the
area upstream of the last point of each basin, like the dams and the one defined in HAT, since in Hybrid 2D we cannot
run the 2D model for each upstream point."

The network, areas in km2, every subbasin CN 100 with no initial abstraction, so the excess is the reduced rain:

    A 0.01 -> J <- B 0.02             J, a junction, named a last point       J: 0.03
    J -> RJ -> Out
    C 0.03 -> D1 -> Rd -> D2 <- E 0.04   two dams in series                    D1: 0.03, D2: 0.07
    D2 -> Rb -> K <- F 0.05            K a junction, no last point at or below F
    K -> Out

The curve falls linearly from 1 at 0 km2 to 0.5 at 0.1 km2, so the factor is 1 - 5 x area, by hand: 0.85 at 0.03 km2
(J, D1), 0.65 at D2's 0.07, and 0.95, 0.90, 0.80, 0.75 at A, B, E, F's own 0.01, 0.02, 0.04, 0.05.
"""

from __future__ import annotations

import json

import pytest

from tests.engine import test_entry_area as entry_area
from tests.engine import test_left_out as valley
from tests.engine.conftest import X0, job
from tests.engine.test_entry_area import CURVE_SPLIT, DEPTH_MM, LAG, POOL, _element, _storm, _volume
from tests.engine.test_handback import DX, HEAD, MIDDLE, NX, NY, SUB, plane
from wadi2d.config.schema import ENTRY_EDGE, ENTRY_POINT, RunConfig
from wadi2d.engine.last_points import first_last_point, last_points
from wadi2d.engine.left_out import snap_entries
from wadi2d.run import (
    InvalidJob,
    _lumped_basin,
    _lumped_rain,
    _network,
    _resolved,
    job_hash,
    prepare_grid,
    run_job,
)

AREA = {"A": 0.01, "B": 0.02, "C": 0.03, "E": 0.04, "F": 0.05}
DOWN = {"A": "J", "B": "J", "C": "D1", "E": "D2", "F": "K"}
ICON = {"J": (X0 + 100.0, MIDDLE), "RJ": (X0 + 150.0, MIDDLE), "D2": (X0 + 300.0, MIDDLE), "Rb": (X0 + 320.0, MIDDLE),
        "K": (X0 + 340.0, MIDDLE), "D1": (X0 + 250.0, MIDDLE), "Rd": (X0 + 280.0, MIDDLE)}  # fmt: skip


@pytest.fixture
def pools(monkeypatch):
    """W98's two dams on one table (:func:`tests.engine.test_entry_area.pools`)."""
    entry_area.pools.__wrapped__(monkeypatch)


def factor(area: float) -> float:
    return 1.0 - 5.0 * area


def _canvas(name: str) -> str:
    x, y = ICON[name]
    return f"     Canvas X: {x}\n     Canvas Y: {y}\n"


def _sub(name: str) -> str:
    return (
        SUB.replace("Subbasin: Side", f"Subbasin: {name}")
        .replace("Area: 0.1", f"Area: {AREA[name]:g}")
        .format(down=DOWN[name])
    )


def _basin(tmp_path):
    path = tmp_path / "last.basin"
    path.write_text(
        HEAD + _sub("A") + _sub("B") + _element("Junction", "J", "RJ", _canvas("J"))
        + _element("Reach", "RJ", "Out", _canvas("RJ") + LAG)
        + _sub("C") + _element("Reservoir", "D1", "Rd", _canvas("D1") + POOL)
        + _element("Reach", "Rd", "D2", _canvas("Rd") + LAG)
        + _sub("E") + _element("Reservoir", "D2", "Rb", _canvas("D2") + POOL)
        + _element("Reach", "Rb", "K", _canvas("Rb") + LAG)
        + _sub("F") + _element("Junction", "K", "Out", _canvas("K")) + _element("Sink", "Out", None),
        encoding="utf-8",
    )  # fmt: skip
    return path


def _job(tmp_path, points=None, outlets: bool = True, modes: dict | None = None, **parts):
    """Hybrid 2D by default: every subbasin lumped at its own outlet, the lumped part of the reduction a curve."""
    storm = {"kind": "depth", "depth_mm": DEPTH_MM, "duration_min": 60.0, "area_reduction": CURVE_SPLIT}
    modes = modes or {}
    subbasins = [
        {
            "name": n,
            "mode": modes.get(n, "lumped"),
            **({"outlet": [X0 + 20.0 + 40.0 * k, MIDDLE]} if outlets else {}),
        }
        for k, n in enumerate(AREA)
    ]
    hydrology = {"hms_basin": str(_basin(tmp_path)), "time_step_min": 5.0, "subbasins": subbasins,
                 **({"last_points": points} if points is not None else {}), **parts.pop("hydrology", {})}  # fmt: skip
    run = {"duration_s": 4 * 3600.0, "backend": "cpu", **parts.pop("run", {})}
    return job(plane(tmp_path), NX, NY, DX, storm=storm, hydrology=hydrology, run=run, **parts)


def _depth(cfg, name: str) -> float:
    basin, hms, _cut = _lumped_basin(cfg, "")
    return float(_lumped_rain(cfg, _storm(cfg), basin, hms, "").over(name).increments(5.0, 24).sum())


def test_the_last_points_are_the_dams_unless_the_job_names_them(tmp_path, pools) -> None:
    basin = _lumped_basin(_job(tmp_path), "")[0]
    assert last_points(None, basin) == ["D1", "D2"]
    assert last_points(["D1", "D2", "J"], basin) == ["D1", "D2", "J"] and last_points([], basin) == []
    with pytest.raises(ValueError, match="does not hold"):
        last_points(["Nowhere"], basin)
    first = first_last_point(basin, ["D1", "D2", "J"])
    assert {first[n] for n in "AB"} == {"J"} and first["C"] == "D1" and first["D1"] == "D1"
    assert first["Rd"] == "D2" and first["E"] == "D2" and "F" not in first and "K" not in first
    with pytest.raises(InvalidJob, match="Nowhere"):
        _depth(_job(tmp_path, ["Nowhere"]), "A")


def test_hybrid_2d_reads_each_subbasin_at_its_first_last_point(tmp_path, pools) -> None:
    """Every subbasin enters at its own outlet: one factor per last point, the first at or below it."""
    named = _job(tmp_path, ["D1", "D2", "J"])
    expect = {
        "A": factor(0.03),
        "B": factor(0.03),
        "C": factor(0.03),
        "E": factor(0.07),
        "F": factor(AREA["F"]),
    }
    for name, f in expect.items():
        assert _depth(named, name) == pytest.approx(DEPTH_MM * f, rel=1e-12), name
    dams = _job(tmp_path)  # the default: the dams alone, so A and B read their own areas
    for name, f in {**expect, "A": factor(0.01), "B": factor(0.02)}.items():
        assert _depth(dams, name) == pytest.approx(DEPTH_MM * f, rel=1e-12), name
    none = _job(tmp_path, [])  # no last point: W98's rule, every subbasin at its own outlet's area
    for name, area in AREA.items():
        assert _depth(none, name) == pytest.approx(DEPTH_MM * factor(area), rel=1e-12), name
    data = named.model_dump(mode="json")
    data["hydrology"]["subbasins"][3]["storm_area_km2"] = 0.01  # E's own storm area still wins
    assert _depth(RunConfig.model_validate(data), "E") == pytest.approx(DEPTH_MM * factor(0.01), rel=1e-12)


def test_hybrid_2d_series_of_record_are_what_entered(tmp_path, pools) -> None:
    """No rerun: each subbasin enters at itself, and its series is the run at its dam's factor (W98's rule there)."""
    cfg = _job(tmp_path, ["D1", "D2", "J"])
    table, _live, series = _network(cfg, _storm(cfg))
    entering = {name: q for name, _point, _t, q in table}
    assert set(entering) == set(AREA) and series.own_area == {}
    m3 = 1000.0 * DEPTH_MM
    assert _volume(entering["C"]) == pytest.approx(AREA["C"] * factor(0.03) * m3, rel=1e-3)
    assert _volume(entering["E"]) == pytest.approx(AREA["E"] * factor(0.07) * m3, rel=1e-3)
    rows = {row["subbasin"]: row for row in series.record["subbasins"]}
    assert (
        rows["E"]["last_point"] == "D2"
        and rows["E"]["at_last_point"]
        and rows["E"]["factor"] == pytest.approx(0.65)
    )
    assert not rows["F"]["at_last_point"] and rows["F"]["read_at"].startswith("its own area")
    assert "last point" in series.record["rule"] and series.record["last_points"] == ["D1", "D2", "J"]


def _network_job(tmp_path, points=None, **parts):
    """Hybrid Lumped: the water kept on the network, F rain-on-grid so the network meets the grid at K."""
    return _job(
        tmp_path, points, outlets=False, modes={"F": "2d"}, hydrology={"lumped_entry": "network"}, **parts
    )


def test_hybrid_lumped_water_stops_at_the_lowest_last_point(tmp_path, pools) -> None:
    old = _resolved(_network_job(tmp_path, []), "")[0].hydrology.inflows  # W88: down the reaches to the grid
    assert {(i.element, i.entry) for i in old} == {("RJ", ENTRY_POINT), ("Rb", ENTRY_POINT)}
    cfg = _resolved(_network_job(tmp_path, ["D1", "D2", "J"]), "")[0]
    made = {i.element: i for i in cfg.hydrology.inflows}
    assert set(made) == {"J", "D2"}, (
        "D1 passes its water on to D2, a dam above a dam; nothing below a last point"
    )
    assert all(i.entry == ENTRY_EDGE and (i.x, i.y) == ICON[e] and i.enters for e, i in made.items())
    assert all(s.outlet is None for s in cfg.hydrology.subbasins if s.mode == "lumped")
    dams = {i.element for i in _resolved(_network_job(tmp_path), "")[0].hydrology.inflows}
    assert dams == {"RJ", "D2"}, "the default: the dams; J is no last point, so A and B go on down RJ"
    again = _resolved(cfg, "")[0]
    assert [i.name for i in again.hydrology.inflows] == [i.name for i in cfg.hydrology.inflows], (
        "nothing added twice"
    )


def test_hybrid_lumped_hands_the_grid_each_last_point_s_own_hydrograph(tmp_path, pools) -> None:
    """Each point's own upstream area: the grid takes D2's run at D2's area for everything above it, and D1, above it,
    is reported at its own area, HMS's depth-area practice (W98's rule, kept)."""
    cfg = _resolved(_network_job(tmp_path, ["D1", "D2", "J"]), "")[0]
    for name, at in {"A": 0.03, "B": 0.03, "C": 0.07, "E": 0.07}.items():
        assert _depth(cfg, name) == pytest.approx(DEPTH_MM * factor(at), rel=1e-12), name
    table, _live, series = _network(cfg, _storm(cfg))
    m3 = 1000.0 * DEPTH_MM
    assert _volume(series.run.inflow["D2"]) == pytest.approx(0.07 * factor(0.07) * m3, rel=1e-3)
    assert {name for name, *_rest in table} == {"J outflow", "D2 outflow"}
    assert {"C", "D1", "Rd", "E", "A", "B"} <= set(series.own_area) and "D2" not in series.own_area
    d1 = series.own_area["D1"]
    assert _volume(d1.inflow["D1"]) == pytest.approx(0.03 * factor(0.03) * m3, rel=1e-3), "D1 at its own area"


def test_a_last_point_s_inflow_enters_on_the_edge_of_its_catchments(tmp_path) -> None:
    """The valley of W88: Up left out, J below it. An 'edge' inflow ten cells below the edge moves onto it; a 'point'
    inflow there stays; with nothing left out it enters where it is."""
    below = valley.BELOW
    inflow = {"name": "In", "x": below[0], "y": below[1], "element": "J", "entry": ENTRY_EDGE}
    cfg = valley.valley_job(tmp_path, True, hydrology={"inflows": [inflow]})
    tables, _crs = prepare_grid(cfg, tmp_path / "cache")
    (snap,) = snap_entries(cfg, tables, [("In", below, None, None)], tables.left_out)
    assert snap.point[0] == valley.EDGE + valley.DX / 2.0 and "pour point" in snap.note
    far = (
        valley.X0 + 360.0,
        valley.MID + 40.0,
    )  # far down and off the wadi, beyond entry_snap_m: the pour point still
    short = valley.valley_job(tmp_path, True, hydrology={"inflows": [inflow], "entry_snap_m": 10.0})
    (snap,) = snap_entries(short, tables, [("In", far, None, None)], tables.left_out)
    assert snap.point[0] == valley.EDGE + valley.DX / 2.0 and abs(snap.point[1] - valley.MID) < valley.DX
    plain = valley.valley_job(tmp_path, True)
    assert snap_entries(plain, tables, [("In", below, None, None)], tables.left_out) == []
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 0, run.message
    assert abs(run.balance.relative) < 1e-6
    placed = json.loads((tmp_path / "run" / "entries.json").read_text(encoding="utf-8"))
    assert placed[0]["point"][0] == valley.EDGE + valley.DX / 2.0
    kept = valley.valley_job(tmp_path, False, hydrology={"inflows": [inflow]})
    assert run_job(kept, tmp_path / "kept").exit_code == 0
    assert not (tmp_path / "kept" / "entries.json").exists(), "nothing left out: it enters at its point"


def test_jobs_the_last_points_cannot_touch_keep_their_hash(tmp_path, pools) -> None:
    """A job with neither a lumped curve nor the network entry hashes as before the field existed; one with them
    hashes its last points, so a checkpoint of W98's rule is not resumed under W105's."""
    data = _job(tmp_path).model_dump(mode="json")
    data["storm"].pop("area_reduction")
    plain = RunConfig.model_validate(data)
    assert "last_points" not in _hashed(plain), "no curve, no network: the hash it had before the field"
    curve = _job(tmp_path)
    assert "last_points" in _hashed(curve)
    assert job_hash(curve) != job_hash(_job(tmp_path, [])), "with a curve the last points move the rain"
    assert job_hash(curve) == job_hash(RunConfig.model_validate(json.loads(curve.model_dump_json())))


def _hashed(cfg) -> dict:
    """The hydrology part of what the hash reads, caught on its way into the key."""
    import wadi2d.run as run

    seen = {}
    real = run.cache_key

    def catch(parts):
        seen.update(parts["job"]["hydrology"])
        return real(parts)

    run.cache_key = catch
    try:
        run.job_hash(cfg)
    finally:
        run.cache_key = real
    return seen
