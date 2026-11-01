"""Terrain objects and boundaries in the running solver, through the whole pipeline on the CPU."""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem
from wadi2d.config.constants import G
from wadi2d.config.schema import RunConfig
from wadi2d.run import run_job


def maxima(out, name: str) -> np.ndarray:
    with h5py.File(out / "results.h5", "r") as f:
        return f["maxima"][name][()]


def x_index(x: float, cfg: RunConfig) -> int:
    """Column in the padded grid of an easting."""
    return int((x - X0) // cfg.grid.dx) + 1


@pytest.fixture
def box_dem(tmp_path):
    """A 300 x 64 m box at 2 m pixels, 2 % falling east."""
    return write_dem(tmp_path / "box.tif", tilted_box(150, 32, 2.0, 0.02), 2.0)


def filled_box(dem, objects, inflow_q: float, duration: float, **outputs) -> RunConfig:
    """Water enters at the high end of the box; side walls are the grid edge; the low end is a wall."""
    return job(
        dem,
        75,
        16,
        4.0,
        terrain={"objects": objects},
        hydrology={
            "inflows": [
                {
                    "name": "in",
                    "x": X0 + 6.0,
                    "y": Y0 - 32.0,
                    "times_s": [0.0, 1e6],
                    "flows": [inflow_q, inflow_q],
                }
            ],
            "inject_radius": 12.0,
        },
        run={"duration_s": duration, "source_every_s": 10.0},
        outputs=outputs,
    )


def test_crest_line_holds_until_overtopped(box_dem, tmp_path):
    # the bed at the line is 100 - 0.02 * 200 = 96; a crest at 97 holds about 1 m at the line
    line = [(X0 + 200.0, Y0), (X0 + 200.0, Y0 - 64.0)]
    crest = {"kind": "crest_line", "coordinates": line, "z_constant": 97.0}
    probe = [{"name": "dam", "coordinates": line}]
    area_held = 64.0 * 50.0 * 0.5  # a wedge 1 m deep at the line, 50 m long
    q = 2.0
    held_until = area_held / q

    before = filled_box(box_dem, [crest], q, 0.4 * held_until, lines=probe)
    run = run_job(before, tmp_path / "before")
    assert run.exit_code == 0
    assert maxima(tmp_path / "before", "depth")[:, x_index(X0 + 204.0, before) :].max() == 0.0
    assert abs(run.peaks["dam"][0]) < 1e-3

    after = filled_box(box_dem, [crest], q, 3.0 * held_until, lines=probe)
    over = run_job(after, tmp_path / "after")
    assert over.exit_code == 0
    assert maxima(tmp_path / "after", "depth")[:, x_index(X0 + 204.0, after) :].max() > 0.01
    assert over.peaks["dam"][0] > 0.5 * q


def test_wall_stays_dry_behind_at_any_level(box_dem, tmp_path):
    line = [(X0 + 200.0, Y0), (X0 + 200.0, Y0 - 64.0)]
    wall = {"kind": "wall", "coordinates": line}
    cfg = filled_box(box_dem, [wall], 4.0, 2000.0)
    run = run_job(cfg, tmp_path / "wall")
    assert run.exit_code == 0
    assert maxima(tmp_path / "wall", "depth")[:, x_index(X0 + 200.0, cfg) :].max() == 0.0
    assert maxima(tmp_path / "wall", "depth")[:, x_index(X0 + 196.0, cfg)].max() > 2.0


def test_spillway_passes_its_rating(tmp_path):
    # a reservoir held at a fixed level upstream of a spillway, a free fall below it
    nx, ny, pixel, dx = 120, 32, 2.0, 4.0
    z = np.full((ny, nx), 90.0)
    z[:, 62:] = 80.0
    dem = write_dem(tmp_path / "s.tif", z, pixel)
    crest_z, head, c, length = 100.0, 0.8, 2.1, 40.0
    line = [(X0 + 120.0, Y0), (X0 + 120.0, Y0 - 64.0)]
    objects = [
        {"kind": "crest_line", "coordinates": line, "z_constant": 110.0},
        {"kind": "spillway", "coordinates": line, "z_constant": crest_z, "coefficient": c, "length": length},
    ]
    cfg = job(
        dem,
        60,
        16,
        dx,
        terrain={"objects": objects},
        boundaries=[
            {
                "kind": "stage",
                "coordinates": [(X0 + 2.0, Y0), (X0 + 2.0, Y0 - 64.0)],
                "stage": crest_z + head,
            },
            {"kind": "free", "coordinates": [(X0 + 238.0, Y0), (X0 + 238.0, Y0 - 64.0)]},
        ],
        run={"duration_s": 900.0, "source_every_s": 30.0, "balance_every": 1},
        outputs={"lines": [{"name": "sp", "coordinates": line}], "series_every_s": 5.0},
    )
    run = run_job(cfg, tmp_path / "s")
    assert run.exit_code == 0
    with h5py.File(tmp_path / "s" / "results.h5", "r") as f:
        q = f["series/lines/sp/discharge_m3s"][()]
    assert abs(q[-40:].mean()) == pytest.approx(c * length * head**1.5, rel=0.02)


def test_stage_boundary_fills_to_its_level(tmp_path):
    # flat bed at 10 m, stage 11 m at the west end: the box fills to 1 m and stops
    dem = write_dem(tmp_path / "f.tif", np.full((32, 64), 10.0), 2.0)
    cfg = job(
        dem,
        32,
        16,
        4.0,
        boundaries=[{"kind": "stage", "coordinates": [(X0 + 2.0, Y0), (X0 + 2.0, Y0 - 64.0)], "stage": 11.0}],
        run={"duration_s": 3000.0, "source_every_s": 30.0, "balance_every": 1},
        outputs={"points": [{"name": "far", "x": X0 + 110.0, "y": Y0 - 32.0}]},
    )
    run = run_job(cfg, tmp_path / "f")
    assert run.exit_code == 0
    with h5py.File(tmp_path / "f" / "results.h5", "r") as f:
        level = f["series/points/far/level_m"][()]
    assert level[-40:].mean() == pytest.approx(11.0, abs=0.02)
    assert abs(run.balance.relative) < 1e-3
    assert run.balance.outflow < 0.0


def test_free_boundary_drains_a_tilted_box(tmp_path):
    dem = write_dem(tmp_path / "t.tif", tilted_box(64, 32, 2.0, 0.02), 2.0)
    cfg = job(
        dem,
        32,
        16,
        4.0,
        storm={"kind": "uniform", "depth_mm": 30.0, "duration_min": 5.0},
        boundaries=[{"kind": "free", "coordinates": [(X0 + 126.0, Y0), (X0 + 126.0, Y0 - 64.0)]}],
        run={"duration_s": 3600.0, "source_every_s": 30.0, "balance_every": 1},
    )
    run = run_job(cfg, tmp_path / "t")
    assert run.exit_code == 0
    assert run.balance.outflow > 0.9 * run.balance.rain
    assert abs(run.balance.relative) < 1e-3


def test_normal_boundary_passes_normal_depth(tmp_path):
    # a uniform inflow on a 1 % plane: the depth at the outlet must sit near the Manning normal depth
    slope, n, q_unit = 0.01, 0.03, 1.0
    dem = write_dem(tmp_path / "n.tif", tilted_box(200, 32, 2.0, slope), 2.0)
    width = 64.0
    cfg = job(
        dem,
        100,
        16,
        4.0,
        terrain={"manning": n},
        hydrology={
            "inflows": [
                {
                    "name": "in",
                    "x": X0 + 6.0,
                    "y": Y0 - 32.0,
                    "times_s": [0.0, 1e6],
                    "flows": [q_unit * width, q_unit * width],
                }
            ],
            "inject_radius": 40.0,
        },
        boundaries=[
            {"kind": "normal", "coordinates": [(X0 + 398.0, Y0), (X0 + 398.0, Y0 - 64.0)], "slope": slope}
        ],
        run={"duration_s": 1800.0, "source_every_s": 10.0, "balance_every": 1},
        outputs={"points": [{"name": "p", "x": X0 + 380.0, "y": Y0 - 32.0}]},
    )
    run = run_job(cfg, tmp_path / "n")
    assert run.exit_code == 0
    with h5py.File(tmp_path / "n" / "results.h5", "r") as f:
        h = f["series/points/p/mean_depth_m"][()]
    normal = (q_unit * n / np.sqrt(slope)) ** 0.6
    assert h[-20:].mean() == pytest.approx(normal, rel=0.1)
    froude = q_unit / (h[-20:].mean() * np.sqrt(G * h[-20:].mean()))
    assert 0.5 < froude < 3.0
    assert abs(run.balance.relative) < 1e-3
