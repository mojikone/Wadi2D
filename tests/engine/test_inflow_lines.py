"""Flow hydrograph lines (W61): a hydrograph brought in across a line, shared by conveyance, kept to the cubic metre."""

from __future__ import annotations

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
from wadi2d.config.schema import RunConfig
from wadi2d.engine.inflow_lines import LineInjection
from wadi2d.run import job_hash, run_job

SLOPE, MANNING = 0.01, 0.04
OUTLET = {"kind": "free", "coordinates": [(X0 + 398.0, Y0 + 2.0), (X0 + 398.0, Y0 - 98.0)]}
WEST = [(X0 + 2.0, Y0 - 1.0), (X0 + 2.0, Y0 - 95.0)]
"""Across the whole width, 96 m, in the first column of cells."""


@pytest.fixture
def plane(tmp_path):
    """400 x 96 m falling 1 % east, walls north and south: a wide channel."""
    return write_dem(tmp_path / "plane.tif", tilted_box(200, 48, 2.0, SLOPE), 2.0)


def plane_job(dem, line: dict, duration: float, **parts) -> RunConfig:
    return job(
        dem, 100, 24, 4.0,
        terrain={"manning": MANNING},
        boundaries=[line, OUTLET],
        run={"duration_s": duration, "backend": "cpu", "source_every_s": 10.0},
        outputs={"points": [{"name": "mid", "x": X0 + 250.0, "y": Y0 - 48.0}], "series_every_s": 60.0},
        **parts,
    )  # fmt: skip


def flow_line(coordinates, **flow) -> dict:
    return {"kind": "flow", "coordinates": coordinates, "flow": flow}


def normal_depth(q: float, width: float) -> float:
    return (q / width * MANNING / np.sqrt(SLOPE)) ** 0.6


def test_a_csv_hydrograph_enters_whole_and_the_books_close(plane, tmp_path):
    table = tmp_path / "inflow.csv"
    table.write_text("minutes,flow_m3s\n0,0\n5,2\n15,2\n20,0\n", encoding="utf-8")
    run = run_job(plane_job(plane, flow_line(WEST, file=str(table)), 1800.0), tmp_path / "run")
    assert run.exit_code == 0, run.message
    volume = 2.0 * (2.5 + 10.0 + 2.5) * 60.0
    assert run.balance.inflow == pytest.approx(volume, rel=1e-6)
    assert abs(run.balance.relative) < 1e-6
    assert run.balance.outflow > 0.0


@pytest.mark.parametrize("distribution", ["normal_depth", "conveyance"])
def test_a_steady_flow_reaches_normal_depth(plane, tmp_path, distribution):
    q = 20.0
    line = flow_line(WEST, times_s=[0.0, 1e5], flows=[q, q], distribution=distribution, slope=SLOPE)
    run = run_job(plane_job(plane, line, 2400.0), tmp_path / distribution)
    assert run.exit_code == 0, run.message
    rows = (tmp_path / distribution / "series" / "point_mid.csv").read_text(encoding="utf-8").splitlines()
    heading = rows[0].split(",")
    last = [float(v) for v in rows[-1].split(",")]
    depth = last[heading.index("mean_depth_m")]
    assert depth == pytest.approx(normal_depth(q, 96.0), rel=0.03)
    assert abs(run.balance.relative) < 1e-6


def test_a_line_oblique_to_the_grid_shares_by_its_length_in_each_cell(plane, tmp_path):
    """At 45 degrees across the channel: every cell's width is the line inside it, the flow still reaches normal depth."""
    q = 20.0
    oblique = [(X0 + 2.0, Y0 - 1.0), (X0 + 96.0, Y0 - 95.0)]
    run = run_job(plane_job(plane, flow_line(oblique, times_s=[0.0, 1e5], flows=[q, q]), 2400.0), tmp_path / "o")
    assert run.exit_code == 0, run.message
    assert abs(run.balance.relative) < 1e-6
    assert run.balance.inflow == pytest.approx(q * 2400.0, rel=1e-6)
    rows = (tmp_path / "o" / "series" / "point_mid.csv").read_text(encoding="utf-8").splitlines()
    depth = float(rows[-1].split(",")[rows[0].split(",").index("mean_depth_m")])
    assert depth == pytest.approx(normal_depth(q, 96.0), rel=0.03)


def test_normal_depth_shares_a_flat_line_evenly_and_a_step_by_conveyance():
    flat = np.zeros((3, 2))
    inj = LineInjection(
        "t", np.arange(3), None, 0, np.array([0.0, 1.0]), np.array([1.0, 1.0]), 0.001,
        width=np.full(3, 4.0), manning=np.full(3, 0.04), ground=np.array([0.0, 0.0, 0.5]),
        hc=np.zeros(3), dtab=flat, slope=0.01,
    )  # fmt: skip
    w = inj.weights(np.zeros(3), 1.0)
    level = inj.level
    k = 4.0 / 0.04 * np.maximum(level - inj.ground, 0.0) ** (5.0 / 3.0)
    assert np.sqrt(0.01) * k.sum() == pytest.approx(1.0, rel=1e-9)
    assert w[0] == pytest.approx(w[1]) and w.sum() == pytest.approx(1.0)
    assert w[2] == pytest.approx(k[2] / k.sum())


def test_a_job_without_flow_lines_keeps_its_hash(plane, monkeypatch):
    """The hash sees the boundaries as they were before W61: no ``name``, no ``flow`` key."""
    from wadi2d import run as wadi2d_run

    seen = {}
    monkeypatch.setattr(wadi2d_run, "cache_key", lambda payload: seen.setdefault("p", payload) and "k")
    job_hash(plane_job(plane, {"kind": "stage", "coordinates": WEST, "stage": 99.0}, 60.0))
    lines = seen["p"]["job"]["boundaries"]
    assert all("flow" not in b and "name" not in b for b in lines)
    assert set(lines[0]) == {"kind", "coordinates", "stage", "slope", "snap_m", "min_share"}


def test_a_flow_line_needs_its_hydrograph():
    with pytest.raises(ValueError, match="flow hydrograph"):
        RunConfig.model_validate({"boundaries": [{"kind": "flow", "coordinates": WEST}]})
    with pytest.raises(ValueError, match="either file"):
        RunConfig.model_validate({"boundaries": [{"kind": "flow", "coordinates": WEST, "flow": {}}]})


@pytest.mark.parametrize("kind", ["quadtree", "strip"])
def test_a_flow_line_on_a_mesh_and_beside_a_strip_enters_whole(tmp_path, kind):
    q = 5.0
    if kind == "quadtree":
        pytest.importorskip("whitebox")
        dem = write_dem(tmp_path / "p.tif", tilted_box(200, 48, 2.0, SLOPE), 2.0)
        extra = {
            "mesh": {
                "enabled": True, "coarse_dx": 8.0, "min_dx": 4.0, "analysis_pixel": 2.0,
                "stream_area_fine_km2": 100.0, "stream_area_mid_km2": 100.0,
            }
        }  # fmt: skip
    else:
        dem = write_dem(tmp_path / "p.tif", tilted_box(200, 48, 2.0, SLOPE), 2.0)
        extra = {
            "strips": {
                "enabled": True,
                "corridors": [
                    {"name": "mid", "centre": [(X0 + 60.0, Y0 - 48.0), (X0 + 300.0, Y0 - 48.0)],
                     "offsets": [-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0]}
                ],
            }
        }  # fmt: skip
    cfg = plane_job(dem, flow_line(WEST, times_s=[0.0, 1e5], flows=[q, q]), 900.0, **extra)
    run = run_job(cfg, tmp_path / kind)
    assert run.exit_code == 0, run.message
    assert run.balance.inflow == pytest.approx(q * 900.0, rel=1e-6)
    assert abs(run.balance.relative) < 1e-5


def _last_map(run_dir, *names):
    import h5py

    with h5py.File(run_dir / "results.h5", "r") as f:
        maps = f["maps"]
        last = max(maps, key=lambda k: maps[k].attrs["t_s"])
        return [maps[last][n][()] for n in names]


@pytest.mark.parametrize("momentum", [False, True])
def test_momentum_takes_the_bump_off_a_line_against_the_domain_edge(tmp_path, momentum):
    """W70: 3 % plane, 48 m wide, 50 m3/s (Froude 1.2) entering across the west edge. At rest the line's cells stand
    40 % over the depth downstream; with the momentum normal to the line, within 1 %."""
    slope, q, cells = 0.03, 50.0, 12
    dem = write_dem(tmp_path / "steep.tif", tilted_box(200, 2 * cells, 2.0, slope), 2.0)
    west = [(X0 + 2.0, Y0 - 1.0), (X0 + 2.0, Y0 - 4.0 * cells + 1.0)]
    outlet = {"kind": "free", "coordinates": [(X0 + 398.0, Y0 + 2.0), (X0 + 398.0, Y0 - 4.0 * cells - 2.0)]}
    line = flow_line(west, times_s=[0.0, 1e5], flows=[q, q], slope=slope, momentum=momentum)
    cfg = job(
        dem, 100, cells, 4.0, terrain={"manning": MANNING}, boundaries=[line, outlet],
        run={"duration_s": 600.0, "backend": "cpu", "source_every_s": 10.0},
        outputs={"map_every_s": 300.0, "series_every_s": 60.0},
    )  # fmt: skip
    run = run_job(cfg, tmp_path / "run")
    assert run.exit_code == 0, run.message
    assert abs(run.balance.relative) < 1e-6
    (h,) = _last_map(tmp_path / "run", "mean_depth")
    profile = h[:cells, :100].mean(axis=0)
    first = int(np.argmax(profile > 0.0))
    bump = profile[first] / profile[62]
    if momentum:
        assert bump == pytest.approx(1.0, abs=0.01)
    else:
        assert bump > 1.3


def test_a_supercritical_jet_keeps_its_direction(tmp_path):
    """W70: 8 m3/s through a 16 m line on the west edge of a flat dry plain, Froude 4.9 at the line. The jet's edge
    cannot spread faster than 2 c across a flow running at U (half-angle atan(2 / Fr)): at 20 m east the jet carries
    nearly all of Q east inside 8 + 20 * 2 / Fr m of its axis. Entering at rest, the water spreads out of it."""
    q, s, n = 8.0, 0.05, 0.01
    dem = write_dem(tmp_path / "flat.tif", np.full((100, 100), 100.0), 2.0)
    mid = Y0 - 100.0
    line = [(X0 + 2.0, mid + 8.0), (X0 + 2.0, mid - 8.0)]
    hn = (q / 16.0 * n / np.sqrt(s)) ** 0.6
    froude = q / 16.0 / hn / np.sqrt(9.81 * hn)
    envelope = 8.0 + 20.0 * 2.0 / froude
    found = {}
    for momentum in (False, True):
        cfg = job(
            dem, 50, 50, 4.0, terrain={"manning": n},
            boundaries=[flow_line(line, times_s=[0.0, 1e5], flows=[q, q], slope=s, momentum=momentum)],
            run={"duration_s": 40.0, "backend": "cpu", "source_every_s": 5.0},
            outputs={"map_every_s": 20.0, "series_every_s": 20.0},
        )  # fmt: skip
        out = tmp_path / f"jet_{momentum}"
        run = run_job(cfg, out)
        assert run.exit_code == 0, run.message
        assert abs(run.balance.relative) < 1e-6
        (qx,) = _last_map(out, "qx")
        east = qx[:50, 5]  # the west faces of the column 20 m east of the line
        y = (np.arange(50) + 0.5) * 4.0 - 100.0
        inside = np.abs(y) <= envelope
        found[momentum] = (float(east[inside].sum()) / q, float(east.sum()) / q)
    assert found[True][0] > 0.9
    assert found[True][0] > found[False][0] + 0.05


def test_momentum_asked_for_on_a_quadtree_is_refused(tmp_path):
    pytest.importorskip("whitebox")
    dem = write_dem(tmp_path / "p.tif", tilted_box(200, 48, 2.0, SLOPE), 2.0)
    mesh = {
        "enabled": True, "coarse_dx": 8.0, "min_dx": 4.0, "analysis_pixel": 2.0,
        "stream_area_fine_km2": 100.0, "stream_area_mid_km2": 100.0,
    }  # fmt: skip
    line = {**flow_line(WEST, times_s=[0.0, 1e5], flows=[1.0, 1.0], momentum=True), "name": "Upper wadi"}
    run = run_job(plane_job(dem, line, 60.0, mesh=mesh), tmp_path / "refused")
    assert run.exit_code == 2
    assert "Upper wadi: flow.momentum needs the uniform step" in run.message


def test_a_job_without_flow_lines_sets_no_momentum_source(plane, tmp_path, monkeypatch):
    """Old jobs step through exactly the code they always did: no face kick is ever set."""
    from wadi2d.solver.model import Model

    calls = []
    monkeypatch.setattr(Model, "set_momentum", lambda self, kick: calls.append(kick))
    cfg = plane_job(plane, {"kind": "stage", "coordinates": WEST, "stage": 99.0}, 120.0)
    run = run_job(cfg, tmp_path / "old")
    assert run.exit_code == 0, run.message
    assert calls == []


def test_a_flow_line_across_a_corridor_is_refused_by_name(tmp_path):
    dem = write_dem(tmp_path / "p.tif", tilted_box(200, 48, 2.0, SLOPE), 2.0)
    strips = {
        "enabled": True,
        "corridors": [
            {"name": "mid", "centre": [(X0 + 20.0, Y0 - 48.0), (X0 + 300.0, Y0 - 48.0)],
             "offsets": [-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0]}
        ],
    }  # fmt: skip
    across = [(X0 + 100.0, Y0 - 1.0), (X0 + 100.0, Y0 - 95.0)]
    line = {**flow_line(across, times_s=[0.0, 1e5], flows=[1.0, 1.0]), "name": "Upper wadi"}
    run = run_job(plane_job(dem, line, 60.0, strips=strips), tmp_path / "refused")
    assert run.exit_code == 2
    assert "Upper wadi crosses the cells of an aligned corridor" in run.message
