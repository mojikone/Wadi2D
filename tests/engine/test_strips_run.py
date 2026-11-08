"""A job with strips through ``run_job`` (W45, stage 7): a corridor along a rained plane, the books close, the line
across it reads what the same job reads without strips, and a job without strips keeps its hash."""

from __future__ import annotations

import json

import numpy as np
import pytest

from tests.engine.conftest import X0, Y0, job, tilted_dem  # noqa: F401
from wadi2d.run import job_hash, run_job

MID_Y = Y0 - 48.0
LINE = [(X0 + 100.0, Y0 - 16.0), (X0 + 100.0, Y0 - 80.0)]
"""Across the plane at x = 100 m, through the corridor and the tiles either side."""


def plane_job(dem, strips: dict | None):
    parts = dict(
        storm={"kind": "uniform", "depth_mm": 60.0, "duration_min": 20.0},
        boundaries=[{"kind": "free", "coordinates": [(X0 + 201.0, Y0 + 2.0), (X0 + 201.0, Y0 - 98.0)]}],
        outputs={"lines": [{"name": "across", "coordinates": LINE}], "series_every_s": 10.0},
        run={"duration_s": 1800.0, "backend": "cpu", "source_every_s": 10.0},
    )
    if strips is not None:
        parts["strips"] = strips
    return job(dem, 50, 24, 4.0, **parts)


def corridor(x_end: float = 160.0) -> dict:
    return {
        "enabled": True,
        "corridors": [
            {
                "name": "mid",
                "centre": [(X0 + 40.0, MID_Y), (X0 + x_end, MID_Y)],
                "offsets": [-12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0],
                # row 2 lies 4 m to the right of travel (eastward: south), so its line is at MID_Y - 4
                "snap": [{"row": 2, "coordinates": [(X0, MID_Y - 4.0), (X0 + 200.0, MID_Y - 4.0)]}],
            }
        ],
    }


def peak_and_volume(out) -> tuple[float, float]:
    rows = (out / "series" / "line_across.csv").read_text(encoding="utf-8").splitlines()[1:]
    t = np.array([float(r.split(",")[0]) for r in rows])
    q = np.array([float(r.split(",")[1]) for r in rows])
    return float(np.abs(q).max()), float(abs(np.trapezoid(q, t)))


def test_a_job_with_a_corridor_runs_on_the_cpu_and_its_books_close(tilted_dem, tmp_path) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, corridor())
    out = tmp_path / "strips"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    assert run.backend == "cpu"
    events = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    (strips,) = [e for e in events if e.get("ev") == "strips"]
    assert strips["corridors"] == 1 and strips["cells"] == 6 * 30 and strips["triangles"] > 0 and strips["replaced"] > 0
    assert abs(run.balance.relative) < 1e-6
    assert run.balance.rain > 0.0
    import sqlite3

    db = sqlite3.connect(out / "maps" / "strip_mesh.gpkg")
    cells = db.execute("SELECT COUNT(*), MAX(max_depth_m), SUM(kind = 'corridor') FROM strip_cells").fetchone()
    faces = db.execute("SELECT SUM(kind = 'interface'), SUM(kind = 'breakline'), MAX(max_discharge_m3s) FROM strip_faces").fetchone()
    db.close()
    assert cells[0] == strips["cells"] + strips["triangles"] and cells[2] == strips["cells"] and cells[1] > 0.0
    assert faces[0] > 0 and faces[1] == 30 and faces[2] > 0.0  # one snapped row of 30 stations


def test_a_corridor_ending_on_the_outflow_boundary_closes_the_books(tilted_dem, tmp_path) -> None:  # noqa: F811
    """The free boundary opens the cells at x = 200 to 204 m; a corridor to x = 196 m has them as its ghosts, and
    what it passes into them has left the model."""
    cfg = plane_job(tilted_dem, corridor(196.0))
    out = tmp_path / "outlet"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    assert abs(run.balance.relative) < 1e-6, run.balance
    plain = run_job(plane_job(tilted_dem, None), tmp_path / "plain")
    assert run.balance.outflow == pytest.approx(plain.balance.outflow, rel=0.05)
    assert run.balance.outflow > 0.5 * run.balance.rain


def test_the_line_across_the_corridor_reads_what_the_tiles_alone_read(tilted_dem, tmp_path) -> None:  # noqa: F811
    with_strips = run_job(plane_job(tilted_dem, corridor()), tmp_path / "strips")
    without = run_job(plane_job(tilted_dem, None), tmp_path / "plain")
    assert with_strips.exit_code == 0 and without.exit_code == 0
    peak_s, volume_s = peak_and_volume(tmp_path / "strips")
    peak_p, volume_p = peak_and_volume(tmp_path / "plain")
    assert volume_s == pytest.approx(volume_p, rel=0.05)
    assert peak_s == pytest.approx(peak_p, rel=0.1)


def test_a_job_without_strips_keeps_the_hash_it_had(tilted_dem) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, None)
    data = cfg.model_dump(mode="json")
    assert "strips" in data and not data["strips"]["enabled"]
    assert job_hash(cfg) == job_hash(cfg.model_copy(update={"strips": cfg.strips.model_copy(update={"smooth": 9})}))


@pytest.mark.gpu
def test_the_same_job_on_the_gpu_closes_its_books_and_reads_the_cpu_line(tilted_dem, tmp_path) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, corridor())
    on_gpu = cfg.model_copy(update={"run": cfg.run.model_copy(update={"backend": "gpu"})})
    gpu = run_job(on_gpu, tmp_path / "gpu")
    assert gpu.exit_code == 0, gpu.message
    assert gpu.backend == "gpu"
    assert abs(gpu.balance.relative) < 1e-6
    cpu = run_job(cfg, tmp_path / "cpu")
    peak_g, volume_g = peak_and_volume(tmp_path / "gpu")
    peak_c, volume_c = peak_and_volume(tmp_path / "cpu")
    assert cpu.exit_code == 0
    assert volume_g == pytest.approx(volume_c, rel=1e-3)
    assert peak_g == pytest.approx(peak_c, rel=1e-2)


def banks_file(path, left_y: float, right_y: float, x0: float, x1: float):
    """A Suggest-breaklines GeoPackage of one bank pair and its thalweg, as the engine's command writes them."""
    import fiona

    crs = "EPSG:32640"
    bank_schema = {"geometry": "LineString", "properties": {"name": "str", "kind": "str", "side": "str", "area_km2": "float"}}
    with fiona.open(path, "w", driver="GPKG", layer="breaklines", schema=bank_schema, crs=crs) as dst:
        for side, y in (("left", left_y), ("right", right_y)):
            dst.write({
                "geometry": {"type": "LineString", "coordinates": [(x0, y), (x1, y)]},
                "properties": {"name": f"bank {side}", "kind": "stream bank", "side": side, "area_km2": 12.0},
            })  # fmt: skip
    mid = 0.5 * (left_y + right_y)
    with fiona.open(path, "w", driver="GPKG", layer="thalwegs", schema={"geometry": "LineString", "properties": {"area_km2": "float"}}, crs=crs) as dst:
        dst.write({"geometry": {"type": "LineString", "coordinates": [(x0 - 10.0, mid), (x1 + 10.0, mid)]}, "properties": {"area_km2": 12.0}})
    return path


def test_a_job_builds_its_corridor_from_the_suggest_banks_file(tilted_dem, tmp_path) -> None:  # noqa: F811
    banks = banks_file(tmp_path / "suggested_breaklines.gpkg", MID_Y + 4.0, MID_Y - 4.0, X0 + 30.0, X0 + 170.0)
    strips = {"enabled": True, "banks": str(banks), "cell_min_m": 2.0, "cell_max_m": 8.0, "width_fraction": 0.5, "min_length_m": 60.0}
    out = tmp_path / "banks"
    run = run_job(plane_job(tilted_dem, strips), out)
    assert run.exit_code == 0, run.message
    events = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    (built,) = [e for e in events if e.get("ev") == "strips"]
    assert built["corridors"] == 1 and built["cells"] > 0 and built["cut"] == []
    (rule,) = built["rules"]  # the banks 8 m apart: half of that is 4 m, within the bounds, so two cells across
    assert rule["cells_across"] == 2 and rule["rows_outside"] == 1
    assert rule["width_m"] == pytest.approx(8.0, abs=0.5) and rule["across_m"] == pytest.approx(4.0, abs=0.3)
    assert abs(run.balance.relative) < 1e-6
    import sqlite3

    db = sqlite3.connect(out / "maps" / "strip_mesh.gpkg")
    on_banks = db.execute("SELECT COUNT(DISTINCT line) FROM strip_faces WHERE kind = 'breakline'").fetchone()[0]
    db.close()
    assert on_banks == 2  # both banks carry a row of faces


def test_a_ragged_corridor_on_the_thalweg_runs_and_closes_its_books(tilted_dem, tmp_path) -> None:  # noqa: F811
    """His rule: the thalweg drives the cells, fixed cells repeat to the banks; the banks here are 4 m either side on a
    4 m plane, so two cells of 2 m on each side."""
    banks = banks_file(tmp_path / "suggested_breaklines.gpkg", MID_Y + 4.0, MID_Y - 4.0, X0 + 30.0, X0 + 170.0)
    strips = {"enabled": True, "banks": str(banks), "centre": "thalweg", "cell_min_m": 2.0, "min_length_m": 60.0}
    out = tmp_path / "ragged"
    run = run_job(plane_job(tilted_dem, strips), out)
    assert run.exit_code == 0, run.message
    assert abs(run.balance.relative) < 1e-6
    events = [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    (built,) = [e for e in events if e.get("ev") == "strips"]
    (rule,) = built["rules"]
    assert rule["across_m"] == 2.0 and rule["cells_across"] == 4 and built["cells"] > 0
    assert built["cells"] % 4 == 0  # four cells of 2 m across at every station of the straight corridor


def _strip_depths(out) -> list[tuple[float, float, float]]:
    """(x, y, max depth) of every strip cell from the run's strip mesh."""
    import sqlite3

    import shapely

    db = sqlite3.connect(out / "maps" / "strip_mesh.gpkg")
    rows = db.execute("SELECT geom, max_depth_m FROM strip_cells").fetchall()
    db.close()
    out_rows = []
    for blob, depth in rows:
        c = shapely.get_parts(shapely.from_wkb(blob[40:]))[0].centroid
        out_rows.append((c.x, c.y, float(depth)))
    return out_rows


def test_a_cn_raster_and_a_manning_raster_reach_the_corridor_cells(tilted_dem, tmp_path) -> None:  # noqa: F811
    """The squares under a corridor leave the mask, and a raster read on the mask alone gave the strip no curve
    number: Bidah's corridors were refused for 585 rained cells (2026-11-07). The strip's cells now read the raster
    at the squares they stand in, and take their own roughness from a Manning raster instead of one mean."""
    from tests.engine.conftest import write_dem

    cn = write_dem(tmp_path / "cn.tif", np.full((48, 100), 75.0), 2.0)
    rough = write_dem(tmp_path / "n.tif", np.full((48, 100), 0.3), 2.0)
    base = plane_job(tilted_dem, corridor())
    lossy = base.model_copy(update={"terrain": base.terrain.model_copy(update={"cn_raster": str(cn)})})
    run = run_job(lossy, tmp_path / "cn")
    assert run.exit_code == 0, run.message
    assert abs(run.balance.relative) < 1e-6
    full = run_job(base, tmp_path / "full")
    assert 0.2 * full.balance.rain < run.balance.rain < 0.9 * full.balance.rain
    slow = base.model_copy(update={"terrain": base.terrain.model_copy(update={"manning_raster": str(rough)})})
    on_strip = run_job(slow, tmp_path / "rough")
    assert on_strip.exit_code == 0, on_strip.message
    peak_slow, _v = peak_and_volume(tmp_path / "rough")
    peak_fast, _v = peak_and_volume(tmp_path / "full")
    assert peak_slow < 0.8 * peak_fast, (peak_slow, peak_fast)


def test_the_strip_takes_the_roughness_of_the_square_each_cell_stands_in() -> None:
    from tests.strips.test_pixels import two_quads
    from wadi2d.grid.tiles import TileGrid
    from wadi2d.strips.build import strip_manning, strip_squares

    geo, _mesh, _kept, _pix = two_quads()
    _area, cx, cy = geo.areas_centroids()
    dx = 10.0
    x0, y0 = float(cx.min()) - 2 * dx, float(cy.max()) + 2 * dx
    shape = (int(np.ceil((y0 - cy.min()) / dx)) + 2, int(np.ceil((cx.max() - x0) / dx)) + 2)
    grid = TileGrid.from_mask(np.ones(shape, bool), x0, y0, dx)
    sj, si = strip_squares(geo, grid)
    assert np.all((grid.y0 - cy) // dx == sj) and np.all((cx - grid.x0) // dx == si)
    manning = np.arange(shape[0] * shape[1], dtype=np.float64).reshape(shape) * 0.001 + 0.02
    manning[sj[0], si[0]] = np.nan  # a square the raster does not cover
    n = strip_manning(geo, grid, manning, 0.05)
    assert n[0] == 0.05 and np.allclose(n[1:], manning[sj[1:], si[1:]])
    assert strip_manning(geo, grid, 0.03, 0.05) == 0.03


def test_a_curve_number_takes_its_losses_on_the_corridor_as_on_the_squares(tilted_dem, tmp_path) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, corridor())
    lossy = cfg.model_copy(update={"hydrology": cfg.hydrology.model_copy(update={"curve_number": 75.0})})
    full = run_job(cfg, tmp_path / "full")
    less = run_job(lossy, tmp_path / "cn")
    assert full.exit_code == 0 and less.exit_code == 0, (full.message, less.message)
    assert abs(less.balance.relative) < 1e-6
    assert 0.2 * full.balance.rain < less.balance.rain < 0.9 * full.balance.rain, (less.balance.rain, full.balance.rain)
    # the strip's cells took the same excess as the squares: the rain booked is the excess over every cell's area
    depths = _strip_depths(tmp_path / "cn")
    assert max(d for _x, _y, d in depths) > 0.0


def test_an_inflow_on_the_corridor_enters_the_strip(tilted_dem, tmp_path) -> None:  # noqa: F811
    from wadi2d.config.schema import Inflow

    cfg = plane_job(tilted_dem, corridor())
    point = Inflow(name="in", x=X0 + 60.0, y=MID_Y, times_s=[0.0, 600.0, 601.0, 1800.0], flows=[1.0, 1.0, 0.0, 0.0])
    dry_storm = cfg.storm.model_copy(update={"depth_mm": 0.01})
    hydrology = cfg.hydrology.model_copy(update={"inflows": [point], "inject_radius": 6.0})  # on the corridor cells alone
    cfg = cfg.model_copy(update={"storm": dry_storm, "hydrology": hydrology})
    out = tmp_path / "inflow"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    assert run.balance.inflow == pytest.approx(600.0, rel=0.01), run.balance.inflow
    assert abs(run.balance.relative) < 1e-6
    depths = _strip_depths(out)
    downstream = [d for x, y, d in depths if x > X0 + 70.0 and abs(y - MID_Y) < 6.0]
    upstream = [d for x, y, d in depths if x < X0 + 50.0]
    wet_share = float(np.mean([d > 0.02 for d in downstream]))
    assert wet_share > 0.4 and max(upstream) < 0.01, (wet_share, max(upstream))  # the water runs down the corridor
    import rasterio

    with rasterio.open(out / "maps" / "max_depth.tif") as src:
        grid_max = src.read(1)
        grid_max = np.where(grid_max == src.nodata, 0.0, grid_max)
    centre = max(d for x, y, d in depths if abs(y - MID_Y) < 4.0)
    assert centre > 2.0 * float(grid_max.max()) > 0.0, (centre, float(grid_max.max()))  # deepest on the corridor's middle rows


def test_a_stopped_run_with_a_corridor_resumes_to_the_unbroken_run(tilted_dem, tmp_path, monkeypatch) -> None:  # noqa: F811
    from tests.engine.test_resume_exact import series, stop_asked_at
    from wadi2d.engine.monitor import Monitor

    cfg = plane_job(tilted_dem, corridor())
    cfg = cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"progress_every_s": 0.0})})
    out = tmp_path / "broken"
    with monkeypatch.context() as patch:
        patch.setattr(Monitor, "stop_requested", stop_asked_at(905.0))
        stopped = run_job(cfg, out)
    assert stopped.exit_code == 6, stopped.message
    assert stopped.t_end == pytest.approx(910.0, abs=1e-6)
    resumed = run_job(cfg, out, resume=True)
    whole = run_job(cfg, tmp_path / "whole")
    assert resumed.exit_code == 0 and whole.exit_code == 0, (resumed.message, whole.message)
    assert resumed.steps == whole.steps
    assert series(out) == series(tmp_path / "whole")
    assert resumed.balance.storage == pytest.approx(whole.balance.storage, rel=1e-9)
    for name in ("rain", "outflow"):
        assert getattr(resumed.balance, name) == pytest.approx(getattr(whole.balance, name), rel=1e-9), name
    assert _strip_depths(out) == _strip_depths(tmp_path / "whole")


def test_an_initial_level_fills_the_corridor_cells_inside_its_polygon(tilted_dem, tmp_path) -> None:  # noqa: F811
    import rasterio

    from wadi2d.config.schema import InitialLevel

    with rasterio.open(tilted_dem) as src:
        ground = float(next(src.sample([(X0 + 100.0, MID_Y)]))[0])
    box = [(X0 + 80.0, MID_Y + 12.0), (X0 + 120.0, MID_Y + 12.0), (X0 + 120.0, MID_Y - 12.0), (X0 + 80.0, MID_Y - 12.0)]
    cfg = plane_job(tilted_dem, corridor())
    cfg = cfg.model_copy(update={
        "initial_levels": [InitialLevel(coordinates=box, level=ground + 0.5)],
        "storm": cfg.storm.model_copy(update={"depth_mm": 0.01}),
        "run": cfg.run.model_copy(update={"duration_s": 20.0}),
    })  # fmt: skip
    out = tmp_path / "level"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    assert run.balance.storage0 > 100.0, run.balance.storage0  # 40 x 24 m to about 0.5 m, strip cells included
    inside = [d for x, y, d in _strip_depths(out) if X0 + 82.0 < x < X0 + 118.0 and abs(y - MID_Y) < 10.0]
    assert inside and min(inside) > 0.2, (len(inside), min(inside) if inside else None)


@pytest.mark.parametrize("backend", ["cpu", pytest.param("gpu", marks=pytest.mark.gpu)])
def test_local_time_stepping_steps_the_corridor_every_smallest_step(tilted_dem, tmp_path, backend) -> None:  # noqa: F811
    """With the tiles on their own levels the strip runs as the finest class; the water is the uniform run's."""
    cfg = plane_job(tilted_dem, corridor())
    cfg = cfg.model_copy(update={"run": cfg.run.model_copy(update={"backend": backend})})
    stepped = cfg.model_copy(update={"numerics": cfg.numerics.model_copy(update={"local_time_stepping": True})})
    uniform = run_job(cfg, tmp_path / "uniform")
    levels = run_job(stepped, tmp_path / "levels")
    assert uniform.exit_code == 0 and levels.exit_code == 0, (uniform.message, levels.message)
    assert abs(levels.balance.relative) < 1e-6, levels.balance
    peak_u, volume_u = peak_and_volume(tmp_path / "uniform")
    peak_l, volume_l = peak_and_volume(tmp_path / "levels")
    assert volume_l == pytest.approx(volume_u, rel=0.02)
    assert peak_l == pytest.approx(peak_u, rel=0.05)
    assert levels.balance.storage == pytest.approx(uniform.balance.storage, rel=0.05)
