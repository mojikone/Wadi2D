"""What a dock user can reach on a mesh: each path against an answer known without the mesh."""

from __future__ import annotations

import csv
import json
import threading
import time

import h5py
import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, job, write_dem
from tests.engine.test_review import write_raster
from wadi2d.arf import arf_study
from wadi2d.engine.cli import main
from wadi2d.run import job_hash, prepare_grid, run_job

pytest.importorskip("whitebox")

PIXEL, DX, COARSE = 2.0, 4.0, 8.0
NX, NY = 128, 64
"""Cells of DX of the closed box: one coarse tile beside fine ones."""
LONG = 256
"""Cells along the open plane: fine at both ends, coarse between."""
SIDE_X, SIDE_Y = NX * DX, NY * DX
END = LONG * DX
FINE_END = [(X0, Y0), (X0 + 128.0, Y0), (X0 + 128.0, Y0 - SIDE_Y), (X0, Y0 - SIDE_Y)]
MESH = {
    "enabled": True, "coarse_dx": COARSE, "min_dx": 1.0, "analysis_pixel": PIXEL, "stream_area_fine_km2": 100.0,
    "stream_area_mid_km2": 100.0, "zones": [{"coordinates": FINE_END, "dx": DX}],
}  # fmt: skip
QUICK = {"backend": "cpu", "source_every_s": 60.0}


def flat(tmp_path):
    return write_dem(tmp_path / "flat.tif", np.full((NY * 2, NX * 2), 100.0), PIXEL)


def tilted(tmp_path, slope=0.01):
    x = (np.arange(LONG * 2) + 0.5) * PIXEL
    return write_dem(tmp_path / "tilted.tif", np.tile(100.0 - slope * x, (NY * 2, 1)), PIXEL)


def box(dem, **parts):
    """A closed box on a mesh: whatever goes in stays, so the volume is the answer."""
    return job(dem, NX, NY, DX, mesh=MESH, **parts)


def cell_areas(cfg, tmp_path) -> tuple[np.ndarray, np.ndarray]:
    """West-east position and area of every cell. Coarse cells at the edge hang over it, so the mesh's own area is the sum."""
    grid = prepare_grid(cfg, tmp_path / "c")[0].grid
    _rows, cols, _state, areas = grid.cells_of(grid.mask)
    return grid.x0 + (cols + 0.5) * DX, areas


def test_the_box_really_has_two_cell_sizes(tmp_path):
    grid = prepare_grid(box(flat(tmp_path)), tmp_path / "c")[0].grid
    assert sorted(set(grid.level[1:].tolist())) == [0, 1]


def test_a_mesh_on_a_tilted_plane_really_has_two_cell_sizes(tmp_path):
    grid = prepare_grid(_down_the_plane(tilted(tmp_path), True), tmp_path / "c")[0].grid
    assert sorted(set(grid.level[1:].tolist())) == [0, 1]


# depth grid


def test_a_depth_grid_rains_its_own_depth_on_cells_of_both_sizes(tmp_path):
    depths = np.full((NY * 2, NX * 2), 100.0)
    depths[:, NX:] = 300.0
    raster = write_raster(tmp_path / "pmp.tif", depths, X0, Y0, PIXEL)
    pattern = {"time_percent": [0.0, 100.0], "depth_percent": [0.0, 100.0]}
    cfg = box(
        flat(tmp_path),
        storm={"kind": "hypothetical", "depth_grid": str(raster), "duration_min": 60.0, **pattern},
        run={"duration_s": 3600.0, **QUICK},
    )
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message
    x, areas = cell_areas(cfg, tmp_path)
    fell = (np.where(x > X0 + 256.0, 0.3, 0.1) * areas).sum()
    assert run.balance.storage == pytest.approx(fell, rel=1e-3)


def test_a_depth_grid_that_stops_short_is_still_refused_on_a_mesh(tmp_path):
    raster = write_raster(tmp_path / "pmp.tif", np.full((NY * 2, NX), 100.0), X0, Y0, PIXEL)
    cfg = box(
        flat(tmp_path),
        storm={"kind": "uniform", "depth_grid": str(raster), "duration_min": 60.0},
        run={"duration_s": 600.0, **QUICK},
    )
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 2
    assert "no depth" in summary.message


# rasters of the terrain


def test_a_curve_number_raster_reads_cells_of_both_sizes(tmp_path):
    cn = np.full((NY * 2, NX * 2), 90.0)
    cn[:, NX:] = 70.0
    raster = write_raster(tmp_path / "cn.tif", cn, X0, Y0, PIXEL)
    cfg = box(
        flat(tmp_path),
        terrain={"cn_raster": str(raster)},
        storm={"kind": "uniform", "depth_mm": 100.0, "duration_min": 60.0},
        run={"duration_s": 3600.0, **QUICK},
    )
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message

    def excess(number: float) -> float:
        s = (1000.0 / number - 10.0) * 25.4
        return (100.0 - 0.2 * s) ** 2 / (100.0 + 0.8 * s) / 1000.0

    x, areas = cell_areas(cfg, tmp_path)
    fell = (np.where(x > X0 + 256.0, excess(70.0), excess(90.0)) * areas).sum()
    assert run.balance.storage == pytest.approx(fell, rel=2e-3)


def test_a_manning_raster_slows_the_flow_as_on_the_uniform_grid(tmp_path):
    dem = tilted(tmp_path)
    n = write_raster(tmp_path / "n.tif", np.full((NY * 2, NX * 2), 0.06), X0, Y0, PIXEL)
    peaks = {}
    for name, value in (("raster", {"manning_raster": str(n)}), ("number", {"manning": 0.06})):
        cfg = _down_the_plane(dem, mesh=True, terrain=value)
        run = run_job(cfg, tmp_path / name)
        assert run.exit_code == 0, run.message
        peaks[name] = run.peaks["Outlet"][0]
    assert peaks["raster"] == pytest.approx(peaks["number"], rel=1e-3)


def test_a_pool_set_by_level_fills_cells_of_both_sizes(tmp_path):
    ring = [(X0, Y0), (X0 + SIDE_X, Y0), (X0 + SIDE_X, Y0 - SIDE_Y), (X0, Y0 - SIDE_Y), (X0, Y0)]
    cfg = box(
        flat(tmp_path),
        initial_levels=[{"coordinates": ring, "level": 100.5}],
        run={"duration_s": 60.0, **QUICK},
    )
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message
    assert run.balance.storage == pytest.approx(
        0.5 * SIDE_X * SIDE_Y, rel=1e-3
    )  # the ground holds it, overhang or not


# lumped hydrology


def _west(tmp_path):
    feature = {
        "type": "Feature",
        "properties": {"name": "West"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[X0, Y0], [X0 + 256.0, Y0], [X0 + 256.0, Y0 - SIDE_Y], [X0, Y0 - SIDE_Y], [X0, Y0]]
            ],
        },
    }
    path = tmp_path / "subs.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
    return path


@pytest.mark.parametrize("where", [80.0, 300.0], ids=["into a fine cell", "into a coarse cell"])
def test_a_lumped_subbasin_masks_its_rain_and_its_hydrograph_enters_once(tmp_path, where):
    """Rain falls only outside the polygon, which holds cells of both sizes; the hydrograph is the only water inside."""
    flow = 2.0
    cfg = box(
        flat(tmp_path),
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        hydrology={
            "polygons": str(_west(tmp_path)),
            "subbasins": [{"name": "West", "mode": "lumped"}],
            "inflows": [{
                "name": "West", "x": X0 + where, "y": Y0 - 120.0, "times_s": [0.0, 1200.0], "flows": [flow, flow],
            }],
            "inject_radius": 12.0,
        },
        run={"duration_s": 1200.0, **QUICK},
    )  # fmt: skip
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message
    x, areas = cell_areas(cfg, tmp_path)
    rained = 0.02 * areas[x > X0 + 256.0].sum()
    assert run.balance.inflow == pytest.approx(flow * 1200.0, rel=1e-6)
    assert run.balance.rain == pytest.approx(rained, rel=2e-3)
    assert run.balance.storage == pytest.approx(rained + flow * 1200.0, rel=2e-3)


BASIN = """Basin: One
     Version: 4.12
     Unit System: Metric
End:

Subbasin: West
     Area: 0.1
     Downstream: Out

     LossRate: SCS
     Percent Impervious Area: 0
     Curve Number: 100
     Initial Abstraction: 0

     Transform: SCS
     Lag: 10
     Unitgraph Type: STANDARD

     Baseflow: None
End:

Sink: Out
End:
"""


def test_a_subbasin_of_an_hms_basin_runs_lumped_on_a_mesh(tmp_path):
    """The lumped engine's own hydrograph, at the outlet the job gives it, in a coarse cell."""
    path = tmp_path / "one.basin"
    path.write_text(BASIN, encoding="utf-8")
    cfg = box(
        flat(tmp_path),
        storm={"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0},
        hydrology={
            "hms_basin": str(path),
            "polygons": str(_west(tmp_path)),
            "subbasins": [{"name": "West", "mode": "lumped", "outlet": (X0 + 300.0, Y0 - 120.0)}],
            "inject_radius": 12.0,
        },
        run={"duration_s": 7200.0, **QUICK},
    )
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message
    assert run.balance.inflow == pytest.approx(0.02 * 0.1e6, rel=0.03)
    assert abs(run.balance.relative) < 1e-5


def test_a_2d_subbasin_with_its_own_curve_number_on_a_mesh(tmp_path):
    cn = 80.0
    cfg = box(
        flat(tmp_path),
        storm={"kind": "uniform", "depth_mm": 100.0, "duration_min": 60.0},
        hydrology={
            "polygons": str(_west(tmp_path)),
            "subbasins": [{"name": "West", "mode": "2d", "curve_number": cn}],
        },
        run={"duration_s": 3600.0, **QUICK},
    )
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message
    s = (1000.0 / cn - 10.0) * 25.4
    excess = (100.0 - 0.2 * s) ** 2 / (100.0 + 0.8 * s) / 1000.0
    x, areas = cell_areas(cfg, tmp_path)
    fell = (np.where(x > X0 + 256.0, 0.1, excess) * areas).sum()
    assert run.balance.storage == pytest.approx(fell, rel=2e-3)


# structures, boundaries and gauges


def test_a_spillway_on_a_mesh_passes_its_rating(tmp_path):
    z = np.full((NY * 2, LONG * 2), 90.0)
    z[:, 124:] = 80.0
    dem = write_dem(tmp_path / "s.tif", z, PIXEL)
    crest_z, head, c, length = (
        100.0,
        0.8,
        2.1,
        SIDE_Y,
    )  # shorter ones slosh past 900 s on the uniform grid too
    line = [(X0 + 240.0, Y0), (X0 + 240.0, Y0 - SIDE_Y)]
    objects = [
        {"kind": "crest_line", "coordinates": line, "z_constant": 110.0},
        {"kind": "spillway", "coordinates": line, "z_constant": crest_z, "coefficient": c, "length": length},
    ]
    cfg = job(
        dem, LONG, NY, DX, mesh=MESH, numerics={"local_time_stepping": True},
        terrain={"objects": objects},
        boundaries=[
            {"kind": "stage", "coordinates": [(X0 + 2.0, Y0), (X0 + 2.0, Y0 - SIDE_Y)], "stage": crest_z + head},
            {"kind": "free", "coordinates": [(X0 + END - 6.0, Y0), (X0 + END - 6.0, Y0 - SIDE_Y)]},
        ],
        run={"duration_s": 900.0, "source_every_s": 30.0, "backend": "cpu"},
        outputs={"lines": [{"name": "sp", "coordinates": line}], "series_every_s": 5.0, "live_every_s": 0.0},
    )  # fmt: skip
    grid = prepare_grid(cfg, tmp_path / "c")[0].grid
    assert grid.level[1:].max() == 1
    run = run_job(cfg, tmp_path / "s")
    assert run.exit_code == 0, run.message
    with h5py.File(tmp_path / "s" / "results.h5", "r") as f:
        q = f["series/lines/sp/discharge_m3s"][()]
    assert np.abs(q[-40:]).mean() == pytest.approx(c * length * head**1.5, rel=0.03)


def test_a_burn_line_cuts_the_same_ground_on_a_mesh(tmp_path):
    ring = [(X0, Y0), (X0 + SIDE_X, Y0), (X0 + SIDE_X, Y0 - SIDE_Y), (X0, Y0 - SIDE_Y), (X0, Y0)]
    objects = [
        {"kind": "burn_line", "coordinates": [(X0 + 40.0, Y0 - 20.0), (X0 + 40.0, Y0 - 230.0)], "depth": 2.0}
    ]
    parts = {
        "terrain": {"objects": objects},
        "initial_levels": [{"coordinates": ring, "level": 100.5}],
        "run": {"duration_s": 60.0, **QUICK},
    }
    dem = flat(tmp_path)
    mesh = run_job(box(dem, **parts), tmp_path / "mesh")
    plain = run_job(job(dem, NX, NY, DX, **parts), tmp_path / "plain")
    assert mesh.exit_code == 0, mesh.message
    assert mesh.balance.storage == pytest.approx(plain.balance.storage, rel=1e-3)
    assert mesh.balance.storage > 0.5 * SIDE_X * SIDE_Y


def test_a_normal_depth_edge_on_a_mesh_follows_the_uniform_grid(tmp_path):
    dem = tilted(tmp_path)
    edge = [{
        "kind": "normal", "slope": 0.01, "coordinates": [(X0 + END - 6.0, Y0), (X0 + END - 6.0, Y0 - SIDE_Y)],
    }]  # fmt: skip
    peaks = {}
    for name, mesh in (("mesh", True), ("plain", False)):
        run = run_job(_down_the_plane(dem, mesh, boundaries=edge), tmp_path / name)
        assert run.exit_code == 0, run.message
        peaks[name] = run.peaks["Outlet"][0]
    assert peaks["mesh"] == pytest.approx(peaks["plain"], rel=0.05)


def test_a_gauge_in_a_coarse_cell_reads_as_on_the_uniform_grid(tmp_path):
    dem = tilted(tmp_path)
    outputs = _down_the_plane(dem, False).model_dump(mode="json")["outputs"]
    outputs["points"] = [{"name": "gauge", "x": X0 + 640.0, "y": Y0 - 128.0}]
    grid = prepare_grid(_down_the_plane(dem, True, outputs=outputs), tmp_path / "c")[0].grid
    j, i = int((grid.y0 - (Y0 - 128.0)) / DX), int((X0 + 640.0 - grid.x0) / DX)
    assert grid.level[grid.tile_of[j // 32, i // 32]] == 1
    read = {}
    for name, mesh in (("mesh", True), ("plain", False)):
        run = run_job(_down_the_plane(dem, mesh, outputs=outputs), tmp_path / name)
        assert run.exit_code == 0, run.message
        with h5py.File(tmp_path / name / "results.h5", "r") as f:
            read[name] = f["series/points/gauge/level_m"][()].max()
    assert read["mesh"] == pytest.approx(
        read["plain"], abs=0.03
    )  # a wider cell's centre sits up to 2 m away on a 1 % slope


# the depth-area study


def _down_the_plane(dem, mesh: bool, **parts):
    defaults = {
        "terrain": {"manning": 0.04},
        "storm": {"kind": "uniform", "depth_mm": 60.0, "duration_min": 10.0},
        "boundaries": [{"kind": "free", "coordinates": [(X0 + END - 6.0, Y0), (X0 + END - 6.0, Y0 - SIDE_Y)]}],
        "run": {"duration_s": 1500.0, "backend": "cpu", "source_every_s": 30.0},
        "outputs": {
            "lines": [{
                "name": "Outlet", "coordinates": [(X0 + 200.0, Y0 - 2.0), (X0 + 200.0, Y0 - SIDE_Y + 2.0)],
                "drainage_area_km2": 100.0,
            }],
            "series_every_s": 10.0, "live_every_s": 0.0,
        },
    }  # fmt: skip
    defaults.update(parts)
    if mesh:
        defaults["mesh"] = MESH
    return job(dem, LONG, NY, DX, **defaults)


def test_a_depth_area_study_on_a_mesh_follows_the_uniform_grid(tmp_path):
    dem = tilted(tmp_path)
    accumulation = np.tile(np.linspace(1e4, 2e7, LONG // 2, dtype=np.float32), (NY // 2, 1))
    raster = write_raster(tmp_path / "accum.tif", accumulation, X0, Y0, 8.0)
    storm = {
        "kind": "uniform", "depth_mm": 60.0, "duration_min": 10.0,
        "arf": {"areas_km2": [1.0, 1000.0], "factors": [1.0, 0.5], "table_type": "storm-centred ratio"},
    }  # fmt: skip
    arf = {"areas_km2": [10.0, 900.0], "accumulation": str(raster)}
    found = {}
    for name, mesh in (("mesh", True), ("uniform", False)):
        cfg = _down_the_plane(dem, mesh, storm=storm, arf=arf)
        study = arf_study(cfg, tmp_path / name)
        assert study.exit_code == 0, [r.message for r in study.runs]
        found[name] = study
    rows = {
        name: next(csv.DictReader((tmp_path / name / "design_points.csv").open(encoding="utf-8")))
        for name in found
    }
    assert float(rows["mesh"]["design_peak_m3s"]) == pytest.approx(
        float(rows["uniform"]["design_peak_m3s"]), rel=0.05
    )
    with (
        rasterio.open(found["mesh"].composite["max_depth"]) as a,
        rasterio.open(found["uniform"].composite["max_depth"]) as b,
    ):
        assert a.transform == b.transform
        here, plain = a.read(1, masked=True).filled(0.0), b.read(1, masked=True).filled(0.0)
    ny, nx = min(here.shape[0], plain.shape[0]), min(here.shape[1], plain.shape[1])
    here, plain = here[:ny, :nx], plain[:ny, :nx]
    wet = plain > 0.01
    assert np.median(np.abs(here[wet] - plain[wet])) < 0.02


# stop and resume


@pytest.mark.parametrize(
    "backend, wait", [("cpu", 0.5), pytest.param("gpu", 0.1, marks=pytest.mark.gpu)], ids=["cpu", "gpu"]
)
def test_a_stopped_mesh_run_resumes_and_ends_where_an_unbroken_run_ends(tmp_path, backend, wait):
    dem = tilted(tmp_path)
    cfg = _down_the_plane(
        dem,
        True,
        numerics={"local_time_stepping": True},
        run={"duration_s": 1500.0, "backend": backend, "source_every_s": 30.0},
    )
    whole = run_job(cfg, tmp_path / "whole")
    assert whole.exit_code == 0, whole.message
    out = tmp_path / "broken"

    def stop_soon() -> None:
        while not (out / "results.h5").exists():
            time.sleep(0.02)
        time.sleep(wait)
        (out / "stop").touch()

    thread = threading.Thread(target=stop_soon, daemon=True)
    thread.start()
    summary = run_job(cfg, out)
    thread.join()
    assert summary.exit_code == 6
    assert summary.t_end < 1500.0
    done = run_job(cfg, out, resume=True)
    assert done.exit_code == 0, done.message
    assert done.t_end == pytest.approx(1500.0)
    assert abs(done.balance.relative) < 1e-3
    # rain windows restart at the stop: a uniform run moves 0.9 % here, this one 1.4 %
    assert done.peaks["Outlet"][0] == pytest.approx(whole.peaks["Outlet"][0], rel=0.02)


def test_a_mesh_job_is_another_job_to_a_checkpoint_of_the_uniform_grid(tmp_path):
    dem = tilted(tmp_path)
    assert job_hash(_down_the_plane(dem, True)) != job_hash(_down_the_plane(dem, False))


# the dry run


def test_the_dry_run_counts_the_cells_of_the_mesh_and_says_its_time_is_rough(tmp_path, capsys):
    cfg = _down_the_plane(tilted(tmp_path), True)
    path = tmp_path / "job.json"
    path.write_text(json.dumps(cfg.model_dump(mode="json")), encoding="utf-8")
    assert main(["run", str(path), "--out", str(tmp_path / "dry"), "--backend", "cpu", "--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    grid = prepare_grid(cfg, tmp_path / "c")[0].grid
    assert report["cells"] == grid.cell_count
    assert report["cells"] < LONG * NY
    assert report["tiles"] == grid.ntiles - 1
    assert report["wall_s"] > 0.0
    assert "rough" in report["note"]
    assert not (tmp_path / "dry").exists()


def test_the_dry_run_of_a_uniform_job_carries_no_note(tmp_path, capsys):
    cfg = _down_the_plane(tilted(tmp_path), False)
    path = tmp_path / "job.json"
    path.write_text(json.dumps(cfg.model_dump(mode="json")), encoding="utf-8")
    assert main(["run", str(path), "--out", str(tmp_path / "dry"), "--backend", "cpu", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["note"] == ""
