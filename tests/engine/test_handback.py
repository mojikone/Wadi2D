"""The hand-back, through ``run_job``: the proof his decision asks for before any use.

A closed box: a plane falling east, walled all round, so every drop that enters is on the grid or in the network at
the end. A table hydrograph enters in the west, a line takes it across the middle, a lumped network carries it, and
it comes back in the east. Grid storage and network storage are measured separately, the network's by draining it.
"""

from __future__ import annotations

import json
import threading
import time

import h5py
import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.hydrology.from_hms import PairedColumns, ProjectTables
from wadi2d.hydrology.routing import MuskingumCunge
from wadi2d.run import job_hash, load_job, prepare_grid, run_job

PIXEL, DX = 2.0, 4.0
NX, NY = 128, 32
SOUTH = Y0 - NY * DX
LINE_X = X0 + 200.0
MIDDLE = Y0 - NY * DX / 2.0
HEAD = """Basin: Links
     Version: 4.12
     Unit System: Metric
End:

"""
LAG_MIN = 10.0
PEAK, RISE_S = 8.0, 600.0
VOLUME = PEAK * RISE_S
"""A triangle of 2 x RISE_S: the water that enters the box, m3."""
STEP_MIN = 1.0
TOLERANCE = 1e-5
"""What a closed run closes to, as a share of the water that entered."""


def lag_reach(lag: float = LAG_MIN) -> str:
    return f"""Reach: R1
     Downstream: Out

     Route: Lag
     Lag: {lag:g}
End:

"""


MC_REACH = """Reach: R1
     Downstream: Out

     Route: Muskingum Cunge
     Channel: Trapezoid
     Length: 3000
     Energy Slope: 0.01
     Mannings n: 0.04
     Bottom Width: 10
     Side Slope: 1
     Initial Variable: Combined Inflow
     Space-Time Method: Automatic DX and DT
     Index Parameter Type: Index Celerity
     Index Celerity: 2
     Number Subreaches: 1
     Maximum Depth Iterations: 20
     Maximum Route Step Iterations: 30
     Channel Loss: None
End:

"""
POOL = """Reservoir: R1
     Downstream: Out

     Route: Modified Puls
     Routing Curve: Elevation-Area-Outflow
     Initial Elevation: 100
     Elevation-Area Table: EA
     Elevation-Outflow Table: EQ
     Primary Table: Elevation-Area
End:

"""
SINK = """Sink: Out
End:
"""


def write_basin(tmp_path, *elements: str):
    path = tmp_path / "links.basin"
    path.write_text(HEAD + "".join(elements), encoding="utf-8")
    return path


def plane(tmp_path, slope: float = 0.01):
    x = (np.arange(NX * 2) + 0.5) * PIXEL
    return write_dem(tmp_path / "plane.tif", np.tile(100.0 - slope * x, (NY * 2, 1)), PIXEL)


def flood() -> dict:
    return {
        "name": "Flood",
        "x": X0 + 40.0,
        "y": MIDDLE,
        "times_s": [0.0, RISE_S, 2.0 * RISE_S],
        "flows": [0.0, PEAK, 0.0],
    }


def back(element: str = "R1", name: str = "Back") -> dict:
    return {"name": name, "x": X0 + 340.0, "y": MIDDLE, "element": element}


def across(x: float = LINE_X) -> list[tuple[float, float]]:
    return [(x, Y0 + 2.0), (x, SOUTH - 2.0)]


def box(
    tmp_path, basin, duration: float = 5400.0, inflows=None, step: float = STEP_MIN, backend="cpu", **parts
):
    extra = parts.pop("hydrology", {})
    hydrology = {
        "hms_basin": str(basin),
        "time_step_min": step,
        "inject_radius": 6.0,
        "inflows": [flood(), back()] if inflows is None else inflows,
        "handbacks": [{"name": "Line", "coordinates": across(), "element": "R1"}],
        **extra,
    }
    return job(
        plane(tmp_path), NX, NY, DX,
        terrain={"manning": 0.03},
        hydrology=hydrology,
        run={"duration_s": duration, "backend": backend, "source_every_s": 30.0},
        **parts,
    )  # fmt: skip


def series(out, kind: str, name: str, column: str) -> np.ndarray:
    with h5py.File(out / "results.h5", "r") as f:
        return f[f"series/{kind}/{name}/{column}"][()]


def books(run) -> None:
    """Everything that entered is on the grid, in the network, or has left it."""
    b = run.balance
    assert run.exit_code == 0, run.message
    assert b.inflow - b.reentry == pytest.approx(VOLUME, rel=1e-4)
    held = b.storage + b.network_storage + b.network_out
    assert abs(held + b.routing_defect - VOLUME) < TOLERANCE * VOLUME
    assert abs(b.relative) < TOLERANCE
    assert abs(b.whole_relative) < TOLERANCE


def test_water_in_equals_water_out_with_a_plain_lag(tmp_path):
    out = tmp_path / "run"
    run = run_job(box(tmp_path, write_basin(tmp_path, lag_reach(), SINK)), out)
    books(run)
    b = run.balance
    assert b.handback > 0.9 * VOLUME
    assert b.routing_defect == pytest.approx(0.0, abs=1e-6)
    assert 0.0 <= b.network_storage < 1e-3 * VOLUME  # the tail of the recession, still in the lag
    assert b.reentry + b.network_storage == pytest.approx(b.handback, rel=1e-6)


def test_a_plain_lag_gives_the_exact_answer_block_by_block(tmp_path):
    out = tmp_path / "run"
    books(run_job(box(tmp_path, write_basin(tmp_path, lag_reach(), SINK)), out))
    line = series(out, "handbacks", "Line", "inflow_m3s")
    outflow = series(out, "network", "R1", "outflow_m3s")
    shift = int(LAG_MIN / STEP_MIN)
    assert line.max() > 1.0
    np.testing.assert_array_equal(outflow[shift:], line[: line.size - shift])


def test_a_volume_held_in_the_lag_at_the_end_is_booked_as_network_storage(tmp_path):
    """Stopped with the flood inside the reach: not on the grid, not lost."""
    out = tmp_path / "run"
    run = run_job(box(tmp_path, write_basin(tmp_path, lag_reach(30.0), SINK), duration=1500.0), out)
    assert run.exit_code == 0, run.message
    b = run.balance
    line = series(out, "handbacks", "Line", "inflow_m3s")
    step = STEP_MIN * 60.0
    # by hand: the last 30 minutes of inflow have not come out of a 30-minute lag; the run began 25 minutes ago
    assert b.reentry == 0.0
    assert b.network_storage == pytest.approx(line.sum() * step, rel=1e-9)
    assert abs(b.storage + b.network_storage - (b.inflow - b.reentry)) < TOLERANCE * VOLUME
    assert b.routing_defect == pytest.approx(0.0, abs=1e-6)


def test_muskingum_cunge_closes_and_its_own_volume_error_is_named_not_hidden(tmp_path):
    """HMS's Muskingum-Cunge, which the engine replicates, does not conserve volume on a short flood. The books
    show that as the routing defect, and it is exactly what the same reach gives routed by hand, off the grid.
    """
    out = tmp_path / "run"
    run = run_job(box(tmp_path, write_basin(tmp_path, MC_REACH, SINK), duration=7200.0), out)
    assert run.exit_code == 0, run.message
    b = run.balance
    assert abs(b.relative) < TOLERANCE
    assert b.inflow - b.reentry == pytest.approx(VOLUME, rel=1e-4)
    held = b.storage + b.network_storage + b.network_out + b.routing_defect
    assert abs(held - VOLUME) < TOLERANCE * VOLUME
    line = series(out, "handbacks", "Line", "inflow_m3s")
    by_hand = MuskingumCunge(3000.0, 0.01, 0.04, 10.0, 1.0, 2.0).route(
        np.append(line, np.zeros(2000)), STEP_MIN
    )
    gained = (by_hand.sum() - line.sum()) * STEP_MIN * 60.0
    assert abs(gained) > 0.01 * VOLUME
    assert b.routing_defect == pytest.approx(-gained, rel=1e-3)


def test_a_reservoir_in_the_network_below(tmp_path, monkeypatch):
    area = np.array([1.0e3, 1.0e3, 1.0e3])
    levels = np.array([100.0, 101.0, 110.0])
    tables = ProjectTables(
        {}, {}, {"EA": PairedColumns(levels, area), "EQ": PairedColumns(levels, np.array([0.0, 0.0, 90.0]))}
    )
    monkeypatch.setattr("wadi2d.run._project_tables", lambda _h, _b: tables)
    out = tmp_path / "run"
    run = run_job(box(tmp_path, write_basin(tmp_path, POOL, SINK), duration=9000.0), out)
    assert run.exit_code == 0, run.message
    b = run.balance
    # the dead storage below the 101 m sill, from the table
    assert b.network_storage == pytest.approx(1.0e3, rel=2e-2)
    assert abs(b.routing_defect) < 1e-6 * VOLUME
    assert abs(b.storage + b.network_storage - VOLUME) < TOLERANCE * VOLUME
    assert abs(b.whole_relative) < TOLERANCE


def test_with_no_reentry_the_water_leaves_at_the_end_of_the_network(tmp_path):
    cfg = box(tmp_path, write_basin(tmp_path, lag_reach(), SINK), inflows=[flood()])
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 0, run.message
    b = run.balance
    assert b.reentry == 0.0
    assert b.network_out + b.network_storage == pytest.approx(b.handback, rel=1e-9)
    assert abs(b.whole_relative) < TOLERANCE


def test_two_lines_into_one_reach_are_tallied_apart(tmp_path):
    """Two lines one behind the other, so the second takes what the first misses: here nothing, by the plane."""
    lines = [
        {"name": "North", "coordinates": [(LINE_X, Y0 + 2.0), (LINE_X, MIDDLE)], "element": "R1"},
        {"name": "South", "coordinates": [(LINE_X, MIDDLE), (LINE_X, SOUTH - 2.0)], "element": "R1"},
    ]
    out = tmp_path / "run"
    run = run_job(
        box(tmp_path, write_basin(tmp_path, lag_reach(), SINK), hydrology={"handbacks": lines}), out
    )
    assert run.exit_code == 0, run.message
    north = series(out, "handbacks", "North", "inflow_m3s").sum()
    south = series(out, "handbacks", "South", "inflow_m3s").sum()
    assert north > 0.0
    assert south > 0.0
    assert (north + south) * STEP_MIN * 60.0 == pytest.approx(run.balance.handback, rel=1e-9)
    assert abs(run.balance.whole_relative) < TOLERANCE


def test_nothing_passes_a_line_on_the_grid(tmp_path):
    """Its cells stay dry, so a cell beyond it gets the reach's water and never the same water by the grid as well."""
    out = tmp_path / "run"
    cfg = box(
        tmp_path,
        write_basin(tmp_path, lag_reach(), SINK),
        inflows=[flood()],
        outputs={"lines": [{"name": "Beyond", "coordinates": across(LINE_X + 20.0)}], "series_every_s": 30.0},
    )
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    assert run.balance.handback > 0.9 * VOLUME
    assert np.abs(series(out, "lines", "Beyond", "discharge_m3s")).max() == 0.0


def centroid(t: np.ndarray, q: np.ndarray) -> float:
    return float((t * q).sum() / q.sum())


def test_the_link_puts_one_step_of_lag_on_the_flow(tmp_path):
    """Measured on the grid: a section just before the line, one just after the re-entry, a lag reach between whose
    answer is known exactly. What is left after the reach's own lag is the link's.
    """
    step = 2.0
    sections = [
        {"name": "Before", "coordinates": across(LINE_X - 8.0)},
        {"name": "After", "coordinates": across(X0 + 352.0)},
    ]
    out = tmp_path / "run"
    cfg = box(
        tmp_path, write_basin(tmp_path, lag_reach(), SINK), step=step,
        outputs={"lines": sections, "series_every_s": 10.0},
    )  # fmt: skip
    books(run_job(cfg, out))
    t = series(out, "lines", "Before", "t_s")
    before = series(out, "lines", "Before", "discharge_m3s")
    after = series(out, "lines", "After", "discharge_m3s")
    dt = step * 60.0
    line = series(out, "handbacks", "Line", "inflow_m3s")
    held = series(out, "network", "R1", "outflow_m3s")
    k = np.arange(line.size) * dt
    m = line.size - int(LAG_MIN / step)  # blocks that have come back by the end of the run
    crossed = centroid((k - dt / 2.0)[:m], line[:m])  # a period mean belongs to the middle of its period
    returned = centroid((k + dt / 2.0)[-m:], held[-m:])  # a held flow to the middle of its hold
    link = returned - crossed - LAG_MIN * 60.0
    assert link == pytest.approx(dt, rel=1e-9)
    total = centroid(t, after) - centroid(t, before) - LAG_MIN * 60.0
    grid = total - link
    # the rest is water moving on the grid: 8 m to the line, and from the injection cells to the section 12 m on
    assert 0.0 < grid < 60.0


def test_a_line_that_opens_too_little_warns(tmp_path):
    cfg = box(
        tmp_path,
        write_basin(tmp_path, lag_reach(), SINK),
        hydrology={
            "handbacks": [
                {"name": "Short", "coordinates": [(LINE_X, Y0 - 8.0), (LINE_X, Y0 + 400.0)], "element": "R1"}
            ],
        },
        duration=60.0,
    )
    out = tmp_path / "run"
    assert run_job(cfg, out).exit_code == 0
    events = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    notes = [e["message"] for e in events if e["ev"] == "warn"]
    assert any(n.startswith("Hand-back Short") for n in notes), notes


def test_a_reentry_above_the_line_warns(tmp_path):
    above = {"name": "Back", "x": X0 + 100.0, "y": MIDDLE, "element": "R1"}
    cfg = box(tmp_path, write_basin(tmp_path, lag_reach(), SINK), inflows=[flood(), above], duration=60.0)
    out = tmp_path / "run"
    assert run_job(cfg, out).exit_code == 0
    text = (out / "progress.jsonl").read_text(encoding="utf-8")
    assert "goes round the reach again" in text


SUB = """Subbasin: Side
     Area: 0.1
     Downstream: {down}

     LossRate: SCS
     Percent Impervious Area: 0
     Curve Number: 100
     Initial Abstraction: 0

     Transform: SCS
     Lag: 10
     Unitgraph Type: STANDARD

     Baseflow: None
End:

"""
CHAIN = (
    "Reach: R1\n     Downstream: J\n\n     Route: Lag\n     Lag: 10\nEnd:\n\n"
    "Junction: J\n     Downstream: R2\nEnd:\n\n"
    "Reach: R2\n     Downstream: Out\n\n     Route: Lag\n     Lag: 10\nEnd:\n\n"
)


def side_polygon(tmp_path):
    ring = [[X0, Y0], [X0 + 40.0, Y0], [X0 + 40.0, Y0 - 40.0], [X0, Y0 - 40.0], [X0, Y0]]
    path = tmp_path / "side.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Side"},
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_a_lumped_subbasin_with_an_outlet_below_the_line_enters_the_grid_once_and_not_the_reach(tmp_path):
    """The reach-routed hydrograph stays out of the grid until the end of its reach: a subbasin that enters the grid
    at its own outlet is cut from the reach, so its water is counted once.
    """
    basin = write_basin(tmp_path, SUB.format(down="J"), CHAIN, SINK)
    cfg = box(
        tmp_path,
        basin,
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        hydrology={
            "polygons": str(side_polygon(tmp_path)),
            "subbasins": [{"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE)}],
        },
        inflows=[flood(), back("R2")],
        duration=9000.0,
    )
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 0, run.message
    b = run.balance
    assert b.lateral == 0.0
    assert b.inflow - b.reentry == pytest.approx(VOLUME + 0.02 * 0.1e6, rel=0.01)
    assert abs(b.whole_relative) < TOLERANCE


def test_a_reentry_that_also_carries_a_lumped_subbasin_with_its_own_outlet_is_refused(tmp_path):
    """Above a plain inflow the old rule still holds: the subbasin would enter at its outlet and in the inflow."""
    basin = write_basin(tmp_path, SUB.format(down="J"), CHAIN, SINK)
    cfg = box(
        tmp_path,
        basin,
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        hydrology={
            "polygons": str(side_polygon(tmp_path)),
            "subbasins": [{"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE)}],
            "handbacks": [{"name": "Line", "coordinates": across(), "element": "R1"}],
        },
        inflows=[flood(), back("R1"), {"name": "Lower", "x": X0 + 400.0, "y": MIDDLE, "element": "Out"}],
        duration=60.0,
    )
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 2
    assert "enters twice" in run.message


def test_a_2d_subbasin_inside_the_reach_is_refused_its_rain_would_fall_twice(tmp_path):
    basin = write_basin(tmp_path, SUB.format(down="J"), CHAIN, SINK)
    cfg = box(
        tmp_path,
        basin,
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        inflows=[flood(), back("R2")],
        duration=60.0,
    )
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 2
    assert "falls twice" in run.message


def test_a_2d_subbasin_on_a_route_with_no_reentry_is_refused_too(tmp_path):
    basin = write_basin(tmp_path, SUB.format(down="J"), CHAIN, SINK)
    cfg = box(
        tmp_path,
        basin,
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        inflows=[flood()],
        duration=60.0,
    )
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 2
    assert "falls twice" in run.message


def test_a_lumped_subbasin_joining_the_reach_is_carried_and_booked_once(tmp_path):
    basin = write_basin(tmp_path, SUB.format(down="J"), CHAIN, SINK)
    cfg = box(
        tmp_path,
        basin,
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        hydrology={
            "polygons": str(side_polygon(tmp_path)),
            "subbasins": [{"name": "Side", "mode": "lumped"}],
        },
        inflows=[flood(), back("R2")],
        duration=9000.0,
    )
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 0, run.message
    b = run.balance
    assert b.lateral == pytest.approx(0.02 * 0.1e6, rel=0.02)
    assert abs(b.whole_relative) < TOLERANCE


def test_a_second_handback_on_the_route_is_refused(tmp_path):
    basin = write_basin(tmp_path, CHAIN, SINK)
    lines = [
        {"name": "A", "coordinates": across(), "element": "R1"},
        {"name": "B", "coordinates": across(LINE_X + 40.0), "element": "R2"},
    ]
    run = run_job(box(tmp_path, basin, inflows=[flood()], hydrology={"handbacks": lines}), tmp_path / "run")
    assert run.exit_code == 2
    assert "would be lost" in run.message


def test_two_reentries_on_one_element_are_refused(tmp_path):
    cfg = box(
        tmp_path,
        write_basin(tmp_path, lag_reach(), SINK),
        inflows=[flood(), back(), back(name="Again")],
    )
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 2
    assert "enter twice" in run.message


def test_a_handback_needs_a_network(tmp_path):
    cfg = box(tmp_path, "unused", hydrology={"hms_basin": None}, inflows=[flood()])
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 2
    assert "hand-back needs" in run.message


def test_a_handback_into_an_unknown_element_is_refused(tmp_path):
    lines = [{"name": "Line", "coordinates": across(), "element": "Nowhere"}]
    cfg = box(
        tmp_path, write_basin(tmp_path, lag_reach(), SINK), inflows=[flood()], hydrology={"handbacks": lines}
    )
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 2
    assert "unknown element" in run.message


def test_two_lines_of_one_name_are_refused(tmp_path):
    line = {"name": "Line", "coordinates": across(), "element": "R1"}
    with pytest.raises(ValueError, match="must differ"):
        box(tmp_path, write_basin(tmp_path, lag_reach(), SINK), hydrology={"handbacks": [line, line]})


def test_a_stop_and_a_resume_keep_the_water_in_the_reach(tmp_path):
    basin = write_basin(tmp_path, lag_reach(30.0), SINK)
    cfg = box(tmp_path, basin, duration=7200.0)
    out = tmp_path / "run"

    def stop_soon() -> None:
        while not (out / "results.h5").exists():
            time.sleep(0.02)
        time.sleep(0.5)
        (out / "stop").touch()

    thread = threading.Thread(target=stop_soon, daemon=True)
    thread.start()
    stopped = run_job(cfg, out)
    thread.join()
    assert stopped.exit_code == 6
    assert 0.0 < stopped.t_end < 7200.0
    assert abs(stopped.balance.whole_relative) < 1e-4
    with h5py.File(out / "checkpoint.h5", "r") as f:
        assert "handback" in f
    done = run_job(cfg, out, resume=True)
    assert done.exit_code == 0, done.message
    assert done.t_end == pytest.approx(7200.0)
    whole = run_job(cfg, tmp_path / "whole")
    b = done.balance
    assert abs(b.whole_relative) < TOLERANCE
    assert b.network_storage == pytest.approx(whole.balance.network_storage, abs=1e-3 * VOLUME)
    assert b.storage == pytest.approx(whole.balance.storage, rel=1e-3)
    assert b.handback == pytest.approx(whole.balance.handback, rel=1e-3)


def test_a_checkpoint_without_the_reach_refuses_in_plain_words(tmp_path):
    basin = write_basin(tmp_path, lag_reach(30.0), SINK)
    cfg = box(tmp_path, basin, duration=2400.0)
    out = tmp_path / "run"

    def stop_soon() -> None:
        while not (out / "results.h5").exists():
            time.sleep(0.02)
        time.sleep(0.3)
        (out / "stop").touch()

    thread = threading.Thread(target=stop_soon, daemon=True)
    thread.start()
    assert run_job(cfg, out).exit_code == 6
    thread.join()
    with h5py.File(out / "checkpoint.h5", "r+") as f:
        del f["handback"]
    run = run_job(cfg, out, resume=True)
    assert run.exit_code == 2
    assert "water in the reaches would be lost" in run.message


def test_a_mesh_closes_too(tmp_path):
    pytest.importorskip("whitebox")
    mesh = {
        "enabled": True, "coarse_dx": 8.0, "min_dx": 1.0, "analysis_pixel": PIXEL, "stream_area_fine_km2": 100.0,
        "stream_area_mid_km2": 100.0,
        "zones": [{"coordinates": [(X0, Y0), (X0 + 256.0, Y0), (X0 + 256.0, SOUTH), (X0, SOUTH)], "dx": DX}],
    }  # fmt: skip
    cfg = box(tmp_path, write_basin(tmp_path, lag_reach(), SINK), mesh=mesh, inflows=[flood(), back()])
    grid = prepare_grid(cfg, tmp_path / "c")[0].grid
    assert getattr(grid, "quad", False)
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 0, run.message
    b = run.balance
    assert b.handback > 0.9 * VOLUME
    assert b.routing_defect == pytest.approx(0.0, abs=1e-6)
    assert abs(b.whole_relative) < TOLERANCE


@pytest.mark.gpu
def test_the_books_close_on_the_gpu_as_on_the_cpu(tmp_path):
    basin = write_basin(tmp_path, lag_reach(), SINK)
    run = run_job(box(tmp_path, basin, backend="gpu"), tmp_path / "gpu")
    books(run)
    cpu = run_job(box(tmp_path, basin), tmp_path / "cpu")
    assert run.balance.handback == pytest.approx(cpu.balance.handback, rel=1e-3)


def test_old_jobs_keep_their_hash_their_events_and_their_checkpoints(tmp_path):
    """Nothing about a job without a hand-back or a loss knows these parts exist."""
    dem = plane(tmp_path)
    path = tmp_path / "old.json"
    plain = job(dem, NX, NY, DX, run={"duration_s": 60.0, "backend": "cpu"})
    path.write_text(
        plain.model_dump_json(exclude={"hydrology": {"handbacks"}, "transmission": True}), encoding="utf-8"
    )
    assert job_hash(load_job(path)) == job_hash(plain)
    out = tmp_path / "run"
    done = run_job(plain, out).done
    assert set(done["balance"]) == {
        "rain_m3", "inflow_m3", "outflow_m3", "storage_start_m3", "storage_end_m3", "error_m3", "relative_error",
    }  # fmt: skip
