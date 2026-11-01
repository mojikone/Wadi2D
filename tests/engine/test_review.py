"""Regressions from the independent review: each of these once gave a wrong answer, or lost a run, with no error."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine
from rasterio.warp import transform

from tests.engine.conftest import CRS, X0, Y0, job, tilted_box, write_dem
from wadi2d.arf import arf_study, composite_map, design_table
from wadi2d.config.schema import RunConfig, Terrain, TerrainObject
from wadi2d.engine.estimate import estimate
from wadi2d.engine.hms_import import _outlet
from wadi2d.forcing import Injection, build_storm
from wadi2d.grid import TileGrid
from wadi2d.run import InvalidJob, _project_tables, grid_key, grid_window, job_hash, run_job
from wadi2d.terrain import RasterBed, apply_objects
from wadi2d.terrain.crest import staircase

FLAT = 10.0


def flat_dem(tmp_path: Path, n: int = 32) -> Path:
    return write_dem(tmp_path / "flat.tif", np.full((n, n), FLAT), 2.0)


def rain(depth: float = 100.0, minutes: float = 60.0) -> dict:
    return {"kind": "uniform", "depth_mm": depth, "duration_min": minutes}


def write_raster(path: Path, a: np.ndarray, x0: float, y0: float, res: float, crs: str = CRS) -> Path:
    ny, nx = a.shape
    with rasterio.open(
        path, "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32", nodata=-9999.0, crs=crs,
        transform=Affine(res, 0.0, x0, 0.0, -res, y0),
    ) as dst:  # fmt: skip
        dst.write(np.nan_to_num(a, nan=-9999.0).astype(np.float32), 1)
    return path


def polygons(path: Path, *named: tuple[str, float, float]) -> Path:
    """A FeatureCollection of squares: (name, west offset, side)."""
    features = []
    for name, west, side in named:
        x, y = X0 + west, Y0
        ring = [[x, y], [x + side, y], [x + side, y - side], [x, y - side], [x, y]]
        features.append(
            {
                "type": "Feature",
                "properties": {"name": name},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    crs = {"type": "name", "properties": {"name": CRS}}
    path.write_text(json.dumps({"type": "FeatureCollection", "crs": crs, "features": features}), "utf-8")
    return path


# 1. a storm with no depth


def test_a_storm_without_a_depth_is_refused(tmp_path):
    cfg = job(flat_dem(tmp_path), 16, 16, 4.0, storm={"kind": "uniform", "depth_mm": 0.0})
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 2
    assert "no depth" in summary.message


def test_a_depth_grid_rains_its_own_depth_on_each_cell(tmp_path):
    # 200 mm on the west half, 100 mm on the east half of a closed flat box
    dem = flat_dem(tmp_path)
    depths = np.full((32, 32), 100.0)
    depths[:, :16] = 200.0
    raster = write_raster(tmp_path / "pmp.tif", depths, X0, Y0, 2.0)
    pattern = {"time_percent": [0.0, 100.0], "depth_percent": [0.0, 100.0]}
    cfg = job(
        dem,
        16,
        16,
        4.0,
        storm={"kind": "hypothetical", "depth_grid": str(raster), "duration_min": 60.0, **pattern},
        run={"duration_s": 3600.0, "source_every_s": 60.0},
    )
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message
    assert run.balance.storage == pytest.approx(0.15 * (16 * 4.0) ** 2, rel=1e-3)


def test_a_depth_grid_with_a_hole_under_the_rain_is_refused(tmp_path):
    dem = flat_dem(tmp_path)
    depths = np.full((32, 32), 100.0)
    depths[:, :16] = np.nan
    raster = write_raster(tmp_path / "pmp.tif", depths, X0, Y0, 2.0)
    cfg = job(
        dem, 16, 16, 4.0,
        storm={"kind": "uniform", "depth_grid": str(raster), "duration_min": 60.0},
        run={"duration_s": 600.0},
    )  # fmt: skip
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 2
    assert "no depth" in summary.message


def test_losses_apply_under_a_depth_grid(tmp_path):
    raster = write_raster(tmp_path / "pmp.tif", np.full((32, 32), 100.0), X0, Y0, 2.0)
    cn = 80.0
    cfg = job(
        flat_dem(tmp_path), 16, 16, 4.0,
        storm={"kind": "uniform", "depth_grid": str(raster), "duration_min": 60.0},
        hydrology={"curve_number": cn},
        run={"duration_s": 3600.0, "source_every_s": 60.0},
    )  # fmt: skip
    run = run_job(cfg, tmp_path / "out")
    s = (1000.0 / cn - 10.0) * 25.4
    excess = (100.0 - 0.2 * s) ** 2 / (100.0 + 0.8 * s)
    assert run.balance.storage == pytest.approx(excess / 1000.0 * (16 * 4.0) ** 2, rel=1e-3)


# 2 and 3. lumped water must enter exactly once


def test_a_subbasin_draining_to_a_sink_keeps_its_outlet():
    sink = SimpleNamespace(name="Sink", canvas_x=5.0, canvas_y=6.0)
    model = SimpleNamespace(elements=[sink])
    assert _outlet(model, SimpleNamespace(downstream="Sink")) == (5.0, 6.0)
    assert _outlet(model, SimpleNamespace(downstream=None)) is None


def test_a_lumped_subbasin_with_no_way_in_is_refused(tmp_path):
    subs = polygons(tmp_path / "s.geojson", ("West", 0.0, 32.0))
    cfg = job(
        flat_dem(tmp_path), 16, 16, 4.0,
        storm=rain(), hydrology={"polygons": str(subs), "subbasins": [{"name": "West", "mode": "lumped"}]},
        run={"duration_s": 600.0},
    )  # fmt: skip
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 2
    assert "no way in" in summary.message


def test_a_lumped_subbasin_without_a_polygon_is_refused(tmp_path):
    subs = polygons(tmp_path / "s.geojson", ("Other", 0.0, 32.0))
    cfg = job(
        flat_dem(tmp_path), 16, 16, 4.0,
        storm=rain(),
        hydrology={
            "polygons": str(subs),
            "subbasins": [{"name": "West", "mode": "lumped"}],
            "inflows": [{"name": "West", "x": X0 + 8.0, "y": Y0 - 8.0, "times_s": [0.0, 600.0], "flows": [1.0, 1.0]}],
        },
        run={"duration_s": 600.0},
    )  # fmt: skip
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 2
    assert "without a polygon" in summary.message
    assert summary.balance.rain == 0.0


# 4. rasters in another coordinate system


def test_a_curve_number_raster_in_another_crs_reads_true(tmp_path):
    dem = flat_dem(tmp_path)
    lon, lat = transform(CRS, "EPSG:4326", [X0 - 500.0, X0 + 600.0], [Y0 + 500.0, Y0 - 600.0])
    res = (lon[1] - lon[0]) / 40.0
    cn = write_raster(tmp_path / "cn.tif", np.full((40, 40), 60.0), lon[0], lat[0], res, "EPSG:4326")
    cfg = job(
        dem, 16, 16, 4.0,
        terrain={"cn_raster": str(cn)}, storm=rain(), run={"duration_s": 3600.0, "source_every_s": 60.0},
    )  # fmt: skip
    run = run_job(cfg, tmp_path / "out")
    s = (1000.0 / 60.0 - 10.0) * 25.4
    excess = (100.0 - 0.2 * s) ** 2 / (100.0 + 0.8 * s)
    assert run.balance.storage == pytest.approx(excess / 1000.0 * (16 * 4.0) ** 2, rel=1e-3)


def test_a_hole_in_the_curve_number_raster_is_refused(tmp_path):
    a = np.full((32, 32), 60.0)
    a[:, :8] = np.nan
    cn = write_raster(tmp_path / "cn.tif", a, X0, Y0, 2.0)
    cfg = job(
        flat_dem(tmp_path), 16, 16, 4.0,
        terrain={"cn_raster": str(cn)}, storm=rain(), run={"duration_s": 600.0},
    )  # fmt: skip
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 2
    assert "no CN" in summary.message


def test_a_raster_without_a_crs_cannot_be_matched(tmp_path):
    cn = write_raster(tmp_path / "cn.tif", np.full((32, 32), 60.0), X0, Y0, 2.0, None)
    cfg = job(
        flat_dem(tmp_path), 16, 16, 4.0,
        terrain={"cn_raster": str(cn)}, storm=rain(), run={"duration_s": 600.0},
    )  # fmt: skip
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 2
    assert "no CRS" in summary.message


# 5. crest length


@pytest.mark.parametrize("spacing", [40.0, 10.0, 3.0, 1.0])
def test_crest_length_does_not_depend_on_the_vertex_spacing(spacing):
    grid = TileGrid.from_mask(np.ones((62, 62), bool), 0.0, 620.0, 10.0)
    xs = np.arange(50.0, 450.0 + 1e-6, spacing)
    st = staircase(grid, [(float(x), 303.0) for x in xs])
    assert (st.factor * 10.0).sum() == pytest.approx(xs[-1] - xs[0])
    assert st.size == pytest.approx((xs[-1] - xs[0]) / 10.0, abs=1.0)


def test_diagonal_crest_length_with_close_vertices():
    grid = TileGrid.from_mask(np.ones((62, 62), bool), 0.0, 620.0, 10.0)
    xs = np.arange(50.0, 451.0, 1.0)
    st = staircase(grid, [(float(x), float(x) + 0.3) for x in xs])
    assert (st.factor * 10.0).sum() == pytest.approx(400.0 * np.sqrt(2.0))
    assert st.factor.min() >= 0.0


def test_a_jittery_line_leaves_no_spurs():
    grid = TileGrid.from_mask(np.ones((62, 62), bool), 0.0, 620.0, 10.0)
    points = [(float(x), 305.0 + (1.0 if k % 2 else -1.0)) for k, x in enumerate(np.arange(50.0, 450.0, 3.0))]
    st = staircase(grid, points)
    faces = set(zip(st.axis.tolist(), st.j.tolist(), st.i.tolist(), strict=True))
    assert len(faces) == st.size
    pts = np.array(points)
    assert (st.factor * 10.0).sum() == pytest.approx(np.hypot(*np.diff(pts, axis=0).T).sum())


def crest_flow(tmp_path: Path, name: str, coordinates: list[tuple[float, float]]) -> float:
    dem = write_dem(tmp_path / f"{name}.tif", np.full((64, 120), 100.0), 2.0)
    line = {"kind": "crest_line", "coordinates": coordinates, "z_constant": 101.0}
    west = [(X0 + 2.0, Y0), (X0 + 2.0, Y0 - 128.0)]
    east = [(X0 + 238.0, Y0), (X0 + 238.0, Y0 - 128.0)]
    cfg = job(
        dem, 60, 32, 4.0,
        terrain={"objects": [line]},
        boundaries=[{"kind": "stage", "coordinates": west, "stage": 102.0}, {"kind": "free", "coordinates": east}],
        outputs={"lines": [{"name": "q", "coordinates": [(X0 + 200.0, Y0), (X0 + 200.0, Y0 - 128.0)]}]},
        run={"duration_s": 300.0, "source_every_s": 30.0},
    )  # fmt: skip
    run = run_job(cfg, tmp_path / name)
    assert run.exit_code == 0, run.message
    with h5py.File(tmp_path / name / "results.h5", "r") as f:
        return float(np.abs(f["series/lines/q/discharge_m3s"][()][-10:]).mean())


def test_overtopping_flow_does_not_depend_on_the_vertices(tmp_path):
    ends = crest_flow(tmp_path, "two", [(X0 + 120.0, Y0 - 1.0), (X0 + 120.0, Y0 - 127.0)])
    close = crest_flow(tmp_path, "many", [(X0 + 120.0, Y0 - float(y)) for y in np.arange(1.0, 127.5, 1.0)])
    assert close == pytest.approx(ends, rel=0.01)
    assert ends > 60.0


# 6. inflow far off the domain


def test_an_inflow_far_from_the_domain_is_refused(tmp_path):
    far = {
        "name": "far",
        "x": X0 + 50000.0,
        "y": Y0 + 30000.0,
        "times_s": [0.0, 600.0],
        "flows": [10.0, 10.0],
    }
    cfg = job(flat_dem(tmp_path), 16, 16, 4.0, hydrology={"inflows": [far]}, run={"duration_s": 600.0})
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 2
    assert "inject_max_offset" in summary.message


# 7. hydrograph shape


def test_a_coarse_table_keeps_its_peak_through_the_refresh():
    t = np.array([0.0, 1800.0, 3600.0, 5400.0, 7200.0, 9000.0])
    q = np.array([0.0, 50.0, 400.0, 900.0, 300.0, 0.0])
    inj = Injection("x", np.array([0]), None, 0, t, q, 0.1)
    means = np.array([inj.mean_flow(a, a + 30.0) for a in np.arange(0.0, 9000.0, 30.0)])
    assert means.max() == pytest.approx(900.0, rel=0.01)
    assert (means * 30.0).sum() == pytest.approx(np.trapezoid(q, t))


def test_table_times_must_increase():
    with pytest.raises(ValueError, match="must increase"):
        Injection("x", np.array([0]), None, 0, np.array([0.0, 0.0]), np.array([1.0, 2.0]), 0.1)


# 8. a dry start


def test_a_big_inflow_on_dry_ground_stays_near_its_flow_depth(tmp_path):
    nx, ny, pix, dx = 320, 160, 2.0, 10.0
    dem = write_dem(tmp_path / "d.tif", tilted_box(nx, ny, pix, 0.01), pix)
    width, height = nx * pix, ny * pix
    inflow = {
        "name": "in", "x": X0 + 105.0, "y": Y0 - height / 2,
        "times_s": [0.0, 60.0, 1800.0], "flows": [0.0, 1000.0, 1000.0],
    }  # fmt: skip
    cfg = job(
        dem, nx, ny, pix,
        grid={"dx": dx, "extent": (X0, Y0 - height, X0 + width, Y0)},
        hydrology={"inflows": [inflow]},
        boundaries=[{"kind": "free", "coordinates": [(X0 + width - 5.0, Y0 - 1.0), (X0 + width - 5.0, Y0 - height + 1.0)]}],
        run={"duration_s": 600.0},
    )  # fmt: skip
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message
    with rasterio.open(tmp_path / "out" / "maps" / "max_depth.tif") as src:
        assert src.read(1, masked=True).max() < 6.0
    assert abs(run.balance.relative) < 1e-5


# 9. joints


def regions(grid: TileGrid, crest) -> int:
    """Connected areas of cells across faces no crest closes."""
    from scipy import sparse
    from scipy.sparse.csgraph import connected_components

    ny, nx = grid.shape
    ids = np.arange(ny * nx).reshape(ny, nx)
    open_x = ~np.isfinite(crest.xz[:, 1:])
    open_y = ~np.isfinite(crest.yz[1:, :])
    a = np.concatenate((ids[:, :-1][open_x], ids[:-1, :][open_y]))
    b = np.concatenate((ids[:, 1:][open_x], ids[1:, :][open_y]))
    graph = sparse.coo_matrix((np.ones(a.size), (a, b)), shape=(ny * nx, ny * nx))
    return int(connected_components(graph, directed=False)[0])


def test_a_line_ending_on_another_seals_whichever_was_drawn_first():
    rng = np.random.default_rng(1)
    grid = TileGrid.from_mask(np.ones((62, 62), bool), 10.0, 630.0, 10.0)
    nx = grid.shape[1]
    leaks = 0
    for _ in range(200):
        y0, y1 = rng.uniform(250, 380), rng.uniform(250, 380)
        a = [(grid.x0 - 5.0, y0), (grid.x0 + nx * 10 + 5.0, y1)]
        x = rng.uniform(150, 500)
        ya = y0 + (y1 - y0) * (x - (grid.x0 - 5.0)) / (nx * 10 + 10.0)
        b = [(x + rng.uniform(-40, 40), grid.y0 + 5.0), (x, ya)]
        for pair in ((a, b), (b, a)):
            objects = [TerrainObject(kind="crest_line", coordinates=c, z_constant=5.0) for c in pair]
            crest = apply_objects(grid, objects, 2.0).crest
            leaks += regions(grid, crest) < 3
    assert leaks == 0


def test_a_join_adds_no_length_and_runs_in_the_solver(tmp_path):
    dem = write_dem(tmp_path / "t.tif", np.full((64, 120), 100.0), 2.0)
    dam = [(X0 + 120.0, Y0 + 5.0), (X0 + 120.0, Y0 - 133.0)]
    dyke = [(X0 + 240.0, Y0 - 62.0), (X0 + 127.0, Y0 - 62.0)]
    objects = [
        {"kind": "crest_line", "coordinates": dam, "z_constant": 110.0},
        {"kind": "crest_line", "coordinates": dyke, "z_constant": 110.0},
    ]
    q = {"name": "in", "x": X0 + 200.0, "y": Y0 - 20.0, "times_s": [0.0, 1e6], "flows": [5.0, 5.0]}
    cfg = job(
        dem, 60, 32, 4.0, terrain={"objects": objects}, hydrology={"inflows": [q]},
        run={"duration_s": 900.0, "source_every_s": 30.0},
    )  # fmt: skip
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0, run.message
    with h5py.File(tmp_path / "out" / "results.h5", "r") as f:
        depth = f["maxima/depth"][()]
    assert depth[3:13, 34:58].max() > 0.5
    assert depth[20:30, 34:58].max() == 0.0, "the quarter behind the dam and the dyke must stay dry"
    assert depth[:, :28].max() == 0.0


# 10. paired tables


def test_a_basin_without_reservoirs_reads_no_tables():
    h = SimpleNamespace(hms_basin="x.basin", hms_project=None)
    assert _project_tables(h, SimpleNamespace(reservoirs={}, diversions={})) is None


def test_a_reservoir_basin_without_a_project_is_refused(tmp_path):
    h = SimpleNamespace(hms_basin=str(tmp_path / "x.basin"), hms_project=None)
    with pytest.raises(InvalidJob, match="hms_project"):
        _project_tables(h, SimpleNamespace(reservoirs={"R": 1}, diversions={}))


# 11, 12, 13. stops


def outlet_job(dem: Path, duration: float = 2400.0, **parts) -> RunConfig:
    east = [(X0 + 195.0, Y0), (X0 + 195.0, Y0 - 96.0)]
    return job(
        dem, 50, 24, 4.0,
        storm=rain(30.0, 10.0),
        boundaries=[{"kind": "free", "coordinates": east}],
        run={"duration_s": duration},
        **parts,
    )  # fmt: skip


def test_a_stop_in_the_study_folder_stops_a_study(tilted_dem, tmp_path):
    table = {"areas_km2": [1.0, 100.0], "factors": [1.0, 0.8]}
    line = {"name": "L", "coordinates": [(X0 + 150.0, Y0), (X0 + 150.0, Y0 - 96.0)], "drainage_area_km2": 5.0}
    cfg = outlet_job(tilted_dem, 1e6, arf={"areas_km2": [1.0, 10.0, 100.0]}, outputs={"lines": [line]})
    storm = RunConfig.model_validate({"storm": {**rain(30.0, 10.0), "arf": table}}).storm
    cfg = cfg.model_copy(update={"storm": storm})
    study = tmp_path / "study"
    study.mkdir()

    def stop_soon() -> None:
        while not (study / "runs").exists():
            time.sleep(0.02)
        time.sleep(0.5)
        (study / "stop").touch()

    thread = threading.Thread(target=stop_soon, daemon=True)
    thread.start()
    summary = arf_study(cfg, study)
    thread.join()
    assert summary.exit_code == 6
    assert len(summary.runs) == 1
    assert not (study / "stop").exists()
    assert not (study / "design_points.csv").exists()
    last = json.loads((study / "progress.jsonl").read_text("utf-8").splitlines()[-1])
    assert last["status"] == "stopped"


def test_a_stop_that_was_there_first_is_honoured(tilted_dem, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stop").touch()
    summary = run_job(outlet_job(tilted_dem), out)
    assert summary.exit_code == 6
    assert summary.t_end == 0.0
    assert not (out / "stop").exists()


def test_a_stopped_map_says_it_is_partial(tilted_dem, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stop").touch()
    run_job(outlet_job(tilted_dem), out)
    with rasterio.open(out / "maps" / "max_depth.tif") as src:
        tags = src.tags()
    assert tags["run_status"] == "stopped"
    assert tags["partial"] == "true"
    assert float(tags["t_end_s"]) == 0.0
    done = json.loads((out / "progress.jsonl").read_text("utf-8").splitlines()[-1])
    assert done["ev"] == "done"
    assert done["partial"] is True
    with h5py.File(out / "results.h5", "r") as f:
        assert f.attrs["partial"] == "true"


def test_a_finished_map_says_so(tilted_dem, tmp_path):
    out = tmp_path / "out"
    run_job(outlet_job(tilted_dem, 60.0), out)
    with rasterio.open(out / "maps" / "max_depth.tif") as src:
        assert src.tags()["partial"] == "false"
    done = json.loads((out / "progress.jsonl").read_text("utf-8").splitlines()[-1])
    assert done["partial"] is False


# 14. resume


def test_resume_refuses_another_job_and_leaves_the_folder_alone(tilted_dem, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stop").touch()
    first = outlet_job(tilted_dem)
    assert run_job(first, out).exit_code == 6
    resolved = (out / "config.resolved.json").read_text("utf-8")

    more_rain = first.model_copy(update={"storm": first.storm.model_copy(update={"depth_mm": 150.0})})
    summary = run_job(more_rain, out, resume=True)
    assert summary.exit_code == 2
    assert "another job" in summary.message
    assert (out / "config.resolved.json").read_text("utf-8") == resolved

    other_ground = first.model_copy(update={"terrain": first.terrain.model_copy(update={"manning": 0.1})})
    assert run_job(other_ground, out, resume=True).exit_code == 2
    assert run_job(first, out, resume=True).exit_code == 0


def test_resume_notices_a_changed_input_file(tilted_dem, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "stop").touch()
    cfg = outlet_job(tilted_dem)
    run_job(cfg, out)
    write_dem(tilted_dem, tilted_box(100, 48, 2.0, 0.02), 2.0)
    assert run_job(cfg, out, resume=True).exit_code == 2


def test_the_job_hash_ignores_what_does_not_touch_the_water(tilted_dem):
    cfg = outlet_job(tilted_dem)
    other = cfg.model_copy(
        update={
            "run": cfg.run.model_copy(update={"backend": "gpu", "checkpoint_every_s": 1.0}),
            "project": cfg.project.model_copy(update={"name": "renamed"}),
        }
    )
    assert job_hash(other) == job_hash(cfg)


def test_resume_without_a_checkpoint_says_so(tilted_dem, tmp_path):
    out = tmp_path / "out"
    assert run_job(outlet_job(tilted_dem, 30.0), out, resume=True).exit_code == 0
    assert any('"warn"' in line for line in (out / "progress.jsonl").read_text("utf-8").splitlines())


# 15. the balance


@pytest.mark.parametrize("every", [8, 1])
def test_the_balance_is_exact_at_any_setting(tmp_path, every):
    pix, nx, ny, dx = 2.0, 320, 160, 10.0
    dem = write_dem(tmp_path / "d.tif", np.full((ny, nx), 100.0), pix)
    width, height = nx * pix, ny * pix
    x = X0 + width / 2
    cfg = job(
        dem, nx, ny, pix,
        grid={"dx": dx, "extent": (X0, Y0 - height, X0 + width, Y0)},
        terrain={"objects": [{"kind": "crest_line", "coordinates": [(x, Y0), (x, Y0 - height)], "z_constant": 102.0}]},
        boundaries=[
            {"kind": "stage", "stage": 103.0, "coordinates": [(X0 + 5.0, Y0 - 1.0), (X0 + 5.0, Y0 - height + 1.0)]},
            {"kind": "free", "coordinates": [(X0 + width - 5.0, Y0 - 1.0), (X0 + width - 5.0, Y0 - height + 1.0)]},
        ],
        run={"duration_s": 300.0, "balance_every": every},
    )  # fmt: skip
    run = run_job(cfg, tmp_path / "out")
    assert run.exit_code == 0
    assert abs(run.balance.relative) < 1e-6


@pytest.mark.gpu
def test_the_balance_is_exact_on_the_device(tilted_dem, tmp_path):
    cfg = outlet_job(tilted_dem, 600.0)
    run = run_job(
        cfg.model_copy(update={"run": cfg.run.model_copy(update={"backend": "gpu"})}), tmp_path / "out"
    )
    assert run.backend == "gpu"
    assert run.balance.outflow > 0.0
    assert abs(run.balance.relative) < 1e-5


# 17. the cache key


def test_a_rewritten_domain_file_keeps_its_key_and_a_changed_one_does_not(tilted_dem, tmp_path):
    ring = [[X0, Y0], [X0 + 100.0, Y0], [X0 + 100.0, Y0 - 96.0], [X0, Y0 - 96.0], [X0, Y0]]
    crs = {"type": "name", "properties": {"name": CRS}}
    text = json.dumps({"type": "Polygon", "coordinates": [ring], "crs": crs})
    keys = []
    for name, content in (("a", text), ("b", text), ("c", text.replace("100.0", "100.5", 1) + " ")):
        path = tmp_path / name / "domain.geojson"
        path.parent.mkdir()
        path.write_text(content, "utf-8")
        time.sleep(0.02)
        cfg = job(tilted_dem, 50, 24, 4.0, grid={"dx": 4.0, "extent": None, "domain": str(path)})
        with RasterBed(cfg.terrain.dem) as bed:
            keys.append(grid_key(cfg, bed, grid_window(cfg, bed)))
    assert keys[0] == keys[1]
    assert keys[0] != keys[2]


# 18. the study


def study_job(dem: Path, **storm) -> RunConfig:
    return outlet_job(dem, 300.0, arf={"areas_km2": [1.0, 100.0]}).model_copy(
        update={"storm": RunConfig.model_validate({"storm": {**rain(30.0, 10.0), **storm}}).storm}
    )


def test_a_study_without_a_table_is_refused(tilted_dem, tmp_path):
    summary = arf_study(study_job(tilted_dem), tmp_path / "s")
    assert summary.exit_code == 2
    assert "storm.arf" in summary.message
    assert summary.runs == []


def test_a_study_whose_table_tells_nothing_apart_is_refused(tilted_dem, tmp_path):
    flat = {"areas_km2": [1.0, 100.0], "factors": [0.9, 0.9]}
    summary = arf_study(study_job(tilted_dem, arf=flat), tmp_path / "s")
    assert summary.exit_code == 2
    assert "identical" in summary.message


def test_one_storm_area_gives_a_finite_composite():
    out = composite_map([np.full((3, 3), 2.0)], np.array([100.0]), np.full((3, 3), 50.0))
    np.testing.assert_array_equal(out, np.full((3, 3), 2.0))


def test_one_storm_area_gives_a_design_table(tilted_dem):
    line = {"name": "L", "coordinates": [(0.0, 0.0), (1.0, 0.0)], "drainage_area_km2": 5.0}
    cfg = job(tilted_dem, 50, 24, 4.0, outputs={"lines": [line]})
    rows = design_table(cfg, [10.0], [SimpleNamespace(peaks={"L": (7.0, 60.0)})])
    assert rows[0]["design_peak_m3s"] == pytest.approx(7.0)


# 19. the numbers live in the schema


def test_burn_width_and_spillway_reach_come_from_the_job():
    grid = TileGrid.from_mask(np.ones((30, 30), bool), X0, Y0, 8.0)
    burn = TerrainObject(kind="burn_line", coordinates=[(X0, Y0 - 80.0), (X0 + 200.0, Y0 - 80.0)], depth=3.0)
    z = np.full((64, 64), 50.0)
    apply_objects(grid, [burn], 2.0, Terrain(burn_pixels=1)).edit(z, 0, 0)
    narrow = int((z < 50.0).sum())
    z = np.full((64, 64), 50.0)
    apply_objects(grid, [burn], 2.0, Terrain(burn_pixels=6)).edit(z, 0, 0)
    assert (z < 50.0).sum() > 2 * narrow


# extras: spillways, the dry run, vector inputs


def test_a_spillway_drawn_far_shorter_than_its_length_warns(tmp_path):
    objects = [
        {
            "kind": "spillway", "coordinates": [(X0 + 40.0, Y0 - 10.0), (X0 + 40.0, Y0 - 30.0)],
            "z_constant": 12.0, "length": 100.0,
        }
    ]  # fmt: skip
    cfg = job(flat_dem(tmp_path), 16, 16, 4.0, terrain={"objects": objects}, run={"duration_s": 10.0})
    assert run_job(cfg, tmp_path / "out").exit_code == 0
    assert "drawn" in (tmp_path / "out" / "progress.jsonl").read_text("utf-8")


def test_the_dry_run_uses_the_calibrated_step(tilted_dem):
    cfg = outlet_job(tilted_dem, 3600.0)
    report = estimate(cfg, "cpu")
    assert report.step_s < 1.2
    assert report.wall_s > 0.0


def test_a_polygon_in_degrees_without_a_crs_is_refused(tilted_dem, tmp_path):
    path = tmp_path / "d.geojson"
    ring = [[56.0, 24.0], [56.1, 24.0], [56.1, 24.1], [56.0, 24.0]]
    path.write_text(json.dumps({"type": "Polygon", "coordinates": [ring]}), "utf-8")
    cfg = job(tilted_dem, 50, 24, 4.0, grid={"dx": 4.0, "extent": None, "domain": str(path)})
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 2
    assert "degrees" in summary.message


@pytest.mark.parametrize(("suffix", "driver"), [(".shp", "ESRI Shapefile"), (".gpkg", "GPKG")])
def test_a_domain_can_be_a_shapefile_or_a_geopackage(tilted_dem, tmp_path, suffix, driver):
    fiona = pytest.importorskip("fiona")
    path = tmp_path / f"domain{suffix}"
    ring = [(X0, Y0), (X0 + 100.0, Y0), (X0 + 100.0, Y0 - 96.0), (X0, Y0 - 96.0), (X0, Y0)]
    schema = {"geometry": "Polygon", "properties": {"id": "int"}}
    with fiona.open(path, "w", driver=driver, schema=schema, crs=CRS) as sink:
        sink.write(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"id": 1},
            }
        )
    cfg = job(
        tilted_dem,
        50,
        24,
        4.0,
        grid={"dx": 4.0, "extent": None, "domain": str(path)},
        run={"duration_s": 5.0},
    )
    summary = run_job(cfg, tmp_path / "out")
    assert summary.exit_code == 0, summary.message
    assert summary.cells == 25 * 24


def test_build_storm_passes_the_small_end_rule(tmp_path):
    table = {"areas_km2": [1.0, 100.0], "factors": [0.9, 0.8], "reduces_below_table": False}
    cfg = job("x.tif", 8, 8, 4.0, storm={**rain(100.0), "storm_area_km2": 0.5, "arf": table})
    assert build_storm(cfg).total_depth == pytest.approx(100.0)
