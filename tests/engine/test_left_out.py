"""The 2D mesh leaves out the cells under HMS-routed catchments (W88, the owner's design of 2026-11-15).

A valley falling east, two catchments: ``Up``, the west part, runs lumped and its hydrograph enters below it from the
junction ``J``; the rest is rain on the grid. With ``grid.exclude_lumped`` the cells under ``Up`` leave the mesh. The
water that reaches the outlet must be the full domain's: the left-out cells were dry there, and here they are gone.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import shapely

from tests.engine.conftest import X0, Y0, job, write_dem
from tests.engine.test_handback import HEAD, SINK, SUB
from wadi2d.config.schema import RunConfig
from wadi2d.engine.left_out import LeftOut, choose, snap_entries
from wadi2d.run import (
    InvalidJob,
    NothingOnTheGrid,
    carried_subbasins,
    grid_key,
    job_hash,
    left_out_of,
    prepare_grid,
    run_job,
    strip_key,
)

PIXEL, DX = 2.0, 4.0
NX, NY = 96, 32
SOUTH = Y0 - NY * DX
MID = Y0 - NY * DX / 2.0
EDGE = X0 + 160.0
"""Where ``Up`` ends, on a line between two columns of cells."""
BELOW = (X0 + 200.0, MID - 2.0)
"""An entry ten cells below the edge, on the wadi."""
INSIDE = (X0 + 140.0, MID + 6.0)
"""An entry as an HMS icon may give it: inside the catchment, off the wadi."""
OUT_LINE = [(X0 + 340.0, Y0 + 2.0), (X0 + 340.0, SOUTH - 2.0)]
JUNCTION = "Junction: J\n     Downstream: Out\nEnd:\n\n"


def valley(tmp_path, slope: float = 0.02, side: float = 0.05):
    x = (np.arange(NX * 2) + 0.5) * PIXEL
    y = (np.arange(NY * 2) + 0.5) * PIXEL
    z = 100.0 - slope * x[None, :] + side * np.abs(y[:, None] - NY * DX / 2.0)
    return write_dem(tmp_path / "valley.tif", z, PIXEL)


def ring(x0: float, x1: float, skew: float = 0.0) -> list[list[float]]:
    """A box over the valley's whole width from x0 to x1; ``skew`` moves its east edge's south end."""
    return [[x0, Y0 + 10.0], [x1, Y0 + 10.0], [x1 + skew, SOUTH - 10.0], [x0, SOUTH - 10.0], [x0, Y0 + 10.0]]


def polygons(tmp_path, skew: float = 0.0, **more):
    shapes = {"Up": ring(X0 - 10.0, EDGE, skew), **more}
    features = [
        {"type": "Feature", "properties": {"name": name}, "geometry": {"type": "Polygon", "coordinates": [r]}}
        for name, r in shapes.items()
    ]
    path = tmp_path / "subbasins.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return path


def basin(tmp_path, *more: str):
    path = tmp_path / "valley.basin"
    up = SUB.replace("Subbasin: Side", "Subbasin: Up").format(down="J")
    path.write_text(HEAD + up + "".join(more) + JUNCTION + SINK, encoding="utf-8")
    return path


def valley_job(tmp_path, exclude: bool, entry=BELOW, skew: float = 0.0, **parts) -> RunConfig:
    hydrology = {
        "hms_basin": str(basin(tmp_path)), "time_step_min": 1.0, "inject_radius": 3.0,
        "polygons": str(polygons(tmp_path, skew)),
        "subbasins": [{"name": "Up", "mode": "lumped"}],
        "inflows": [{"name": "In", "x": entry[0], "y": entry[1], "element": "J"}],
        **parts.pop("hydrology", {}),
    }  # fmt: skip
    grid = {"exclude_lumped": exclude, **parts.pop("grid", {})}
    outputs = {"lines": [{"name": "out", "coordinates": OUT_LINE}], "series_every_s": 10.0, **parts.pop("outputs", {})}
    return job(
        valley(tmp_path), NX, NY, DX,
        grid=grid,
        terrain={"manning": 0.03, **parts.pop("terrain", {})},
        storm=parts.pop("storm", {"kind": "uniform", "depth_mm": 20.0, "duration_min": 20.0}),
        hydrology=hydrology,
        boundaries=[{"kind": "free", "coordinates": [(X0 + NX * DX + 1.0, Y0 + 2.0), (X0 + NX * DX + 1.0, SOUTH - 2.0)]}],
        outputs=outputs,
        run={"duration_s": 3600.0, "backend": "cpu", "source_every_s": 10.0, **parts.pop("run", {})},
        **parts,
    )  # fmt: skip


def line(out, name: str = "out") -> tuple[np.ndarray, np.ndarray]:
    rows = (out / "series" / f"line_{name}.csv").read_text(encoding="utf-8").splitlines()[1:]
    t = np.array([float(r.split(",")[0]) for r in rows])
    return t, np.array([float(r.split(",")[1]) for r in rows])


def events(out) -> list[dict]:
    return [json.loads(s) for s in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]


def centres_in(tables, polygon: shapely.Geometry) -> np.ndarray:
    """Cells of the grid whose centre lies in the polygon, by shapely: the rule, read independently."""
    grid = tables.grid
    jj, ii = np.mgrid[0 : grid.shape[0], 0 : grid.shape[1]]
    x, y = grid.xy_of(jj, ii)
    return shapely.contains_xy(polygon, x, y)


def test_the_carried_subbasin_is_found_and_one_with_its_own_outlet_is_not(tmp_path) -> None:
    cfg = valley_job(tmp_path, True)
    assert carried_subbasins(cfg) == {"Up": "In"}
    left = left_out_of(cfg)
    assert left.names == ("Up",) and left.area_km2 == pytest.approx(170.0 * 148.0 / 1e6)
    assert left_out_of(valley_job(tmp_path, False)) is None
    own = valley_job(
        tmp_path, True, hydrology={"subbasins": [{"name": "Up", "mode": "lumped", "outlet": BELOW}], "inflows": []}
    )
    assert carried_subbasins(own) == {}, "it enters at its own outlet: the grid routes its water (run 4's way)"
    assert left_out_of(own).names == ()


@pytest.mark.parametrize("skew", [0.0, 35.0])
def test_the_cells_left_out_are_those_with_their_centre_in_the_polygon(tmp_path, skew: float) -> None:
    full, _crs = prepare_grid(valley_job(tmp_path, False, skew=skew), tmp_path / "cache_full")
    cut, _crs = prepare_grid(valley_job(tmp_path, True, skew=skew), tmp_path / "cache_cut")
    inside = centres_in(full, shapely.Polygon(ring(X0 - 10.0, EDGE, skew)))
    assert full.left_out is None and cut.left_out.names == ("Up",)
    assert cut.grid.shape == full.grid.shape
    assert np.array_equal(cut.grid.mask, full.grid.mask & ~inside)
    assert int(inside[full.grid.mask].sum()) > 1000 and cut.grid.ntiles < full.grid.ntiles
    assert np.array_equal(cut.left_out.on(cut.grid) & full.grid.mask, inside & full.grid.mask)


def test_the_run_without_the_catchment_gives_the_full_domains_outflow(tmp_path) -> None:
    full = run_job(valley_job(tmp_path, False), tmp_path / "full")
    cut = run_job(valley_job(tmp_path, True), tmp_path / "cut")
    assert full.exit_code == 0 and cut.exit_code == 0, (full.message, cut.message)
    assert cut.cells == full.cells - 40 * NY
    assert abs(cut.balance.relative) < 1e-6 and abs(full.balance.relative) < 1e-6
    assert cut.balance.rain == pytest.approx(full.balance.rain, rel=1e-9), "no rim: the rained cells are the same"
    assert cut.balance.inflow == pytest.approx(full.balance.inflow, rel=1e-9)
    assert cut.balance.outflow == pytest.approx(full.balance.outflow, rel=1e-5)
    (t_full, q_full), (t_cut, q_cut) = line(tmp_path / "full"), line(tmp_path / "cut")
    assert np.abs(q_full).max() > 1.0
    assert np.abs(q_cut).max() == pytest.approx(np.abs(q_full).max(), rel=1e-4)
    assert np.trapezoid(q_cut, t_cut) == pytest.approx(np.trapezoid(q_full, t_full), rel=1e-4)
    (said,) = [e for e in events(tmp_path / "cut") if e.get("ev") == "left_out"]
    assert said["subbasins"] == ["Up"] and said["cells"] == 40 * NY and said["owners"] == {"Up": "In"}
    assert not [e for e in events(tmp_path / "full") if e.get("ev") == "left_out"]


def test_no_map_and_no_cell_grid_under_the_catchment(tmp_path) -> None:
    import rasterio

    from wadi2d.products.runner import remake

    run = run_job(valley_job(tmp_path, True, outputs={"map_every_s": 600.0}), tmp_path / "cut")
    assert run.exit_code == 0 and run.products == "finished", run.message
    assert remake(tmp_path / "cut") == 0, "the remake of the maps finds the same mesh from the run's own job"
    for name in ("maps/max_depth.tif", "pixels/pixel_depth.tif"):
        with rasterio.open(tmp_path / "cut" / name) as src:
            depth = np.ma.getmaskarray(src.read(1, masked=True))
            west = src.transform.c + np.arange(depth.shape[1]) * src.transform.a
        mapped = ~depth.all(axis=0)
        assert mapped.any() and west[mapped].min() >= EDGE, f"{name}: nothing is mapped under the left-out catchment"
    import fiona

    with fiona.open(tmp_path / "cut" / "cell_grid.gpkg", layer="cell_grid") as src:
        west = src.bounds[0]
    assert west == EDGE, "the cell grid layer starts at the catchment's edge"


def test_an_entry_inside_the_catchment_moves_to_the_wadi_just_outside(tmp_path) -> None:
    cfg = valley_job(tmp_path, True, entry=INSIDE)
    run = run_job(cfg, tmp_path / "cut")
    assert run.exit_code == 0, run.message
    (record,) = json.loads((tmp_path / "cut" / "entries.json").read_text(encoding="utf-8"))
    x, y = record["point"]
    assert record["name"] == "In" and record["asked"] == list(INSIDE)
    assert x == EDGE + DX / 2.0 and abs(y - MID) == DX / 2.0, "the lowest cell on the catchment's edge: the wadi"
    assert "left out of the mesh" in record["note"]
    at = valley_job(tmp_path, False, entry=(x, y))
    full = run_job(at, tmp_path / "full")
    assert abs(run.balance.relative) < 1e-6
    assert run.balance.inflow == pytest.approx(full.balance.inflow, rel=1e-9)
    assert run.balance.outflow == pytest.approx(full.balance.outflow, rel=1e-3)
    q_cut, q_full = line(tmp_path / "cut")[1], line(tmp_path / "full")[1]
    assert np.abs(q_cut).max() == pytest.approx(np.abs(q_full).max(), rel=0.01), "the wall holds no backwater"


def test_an_entry_with_no_cell_within_reach_stops_the_run_in_words(tmp_path) -> None:
    far = (X0 + 40.0, MID)
    run = run_job(valley_job(tmp_path, True, entry=far, hydrology={"entry_snap_m": 100.0}), tmp_path / "far")
    assert run.exit_code == 2
    assert "left out of the mesh" in run.message and "entry_snap_m" in run.message and "122 m away" in run.message
    reached = valley_job(tmp_path, True, entry=far, hydrology={"entry_snap_m": 150.0})
    tables, _crs = prepare_grid(reached, tmp_path / "cache")
    (snap,) = snap_entries(reached, tables, [("In", far, None, None)], tables.left_out)
    assert snap.point[0] == EDGE + DX / 2.0 and snap.moved_m == pytest.approx(np.hypot(122.0, 2.0))


def test_a_named_subbasin_is_left_out_and_a_2d_one_is_refused(tmp_path) -> None:
    own = {"subbasins": [{"name": "Up", "mode": "lumped", "outlet": INSIDE}], "inflows": []}
    named = valley_job(tmp_path, False, grid={"exclude_subbasins": ["Up"]}, hydrology=own)
    left = left_out_of(named)
    assert left.owner == {"Up": "Up"}
    run = run_job(named, tmp_path / "named")
    assert run.exit_code == 0, run.message
    (record,) = json.loads((tmp_path / "named" / "entries.json").read_text(encoding="utf-8"))
    assert record["name"] == "Up" and record["point"][0] == EDGE + DX / 2.0
    two_d = {"subbasins": [{"name": "Up", "mode": "2d"}], "inflows": []}
    with pytest.raises(InvalidJob, match="not a lumped subbasin"):
        left_out_of(valley_job(tmp_path, False, grid={"exclude_subbasins": ["Up"]}, hydrology=two_d))
    with pytest.raises(ValueError, match="no polygon"):
        choose(named, {}, {})


def test_a_carried_subbasin_gets_no_entry_record_and_the_wall_no_pool_or_pit(tmp_path) -> None:
    """W79's record fault: ``entries.json`` gave every lumped 'wadi' subbasin a point, also one carried by an inflow
    below it, where no water enters. With its cells left out it has no cell to give at all."""
    wadi = {"subbasins": [{"name": "Up", "mode": "lumped", "entry": "wadi"}]}
    for exclude in (False, True):
        out = tmp_path / str(exclude)
        cfg = valley_job(tmp_path, exclude, entry=INSIDE, hydrology=wadi, terrain={"pit_check": True})
        assert run_job(cfg, out).exit_code == 0
        records = json.loads((out / "entries.json").read_text(encoding="utf-8")) if (out / "entries.json").exists() else []
        assert [r["name"] for r in records] == (["In"] if exclude else []), "no record for Up: no water enters there"
        said = " ".join(e.get("message", "") for e in events(out) if e.get("ev") == "warn")
        assert "against the domain edge" not in said, "water running in beside the wall is no pool"
        assert "pit" not in said


def test_a_job_that_carries_nothing_leaves_nothing_out_and_says_so(tmp_path) -> None:
    own = {"subbasins": [{"name": "Up", "mode": "lumped", "outlet": BELOW}], "inflows": []}
    run = run_job(valley_job(tmp_path, True, hydrology=own), tmp_path / "own")
    plain = run_job(valley_job(tmp_path, False, hydrology=own), tmp_path / "plain")
    assert run.exit_code == 0 and run.cells == plain.cells
    assert any("no cell is left out" in e.get("message", "") for e in events(tmp_path / "own"))


def test_everything_left_out_is_no_2d_job(tmp_path) -> None:
    whole = {"polygons": None}
    cfg = valley_job(tmp_path, True, hydrology=whole)
    path = tmp_path / "all.geojson"
    feature = {
        "type": "Feature", "properties": {"name": "Up"},
        "geometry": {"type": "Polygon", "coordinates": [ring(X0 - 10.0, X0 + NX * DX + 10.0)]},
    }  # fmt: skip
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
    cfg = cfg.model_copy(update={"hydrology": cfg.hydrology.model_copy(update={"polygons": str(path)})})
    with pytest.raises(NothingOnTheGrid, match="nothing is left for the 2D model"):
        prepare_grid(cfg, tmp_path / "cache")


def test_a_job_that_leaves_nothing_out_keeps_its_hash_and_its_cache_keys(tmp_path) -> None:
    from wadi2d.run import grid_window
    from wadi2d.terrain import RasterBed

    old = valley_job(tmp_path, False)
    data = old.model_dump(mode="json")
    for name in ("exclude_lumped", "exclude_subbasins"):
        data["grid"].pop(name)
    data["hydrology"].pop("entry_snap_m")
    before = RunConfig.model_validate(data)
    assert "exclude_lumped" not in old.model_dump(mode="json", exclude_defaults=True)["grid"]
    assert job_hash(before) == job_hash(old)
    moved = old.model_copy(update={"hydrology": old.hydrology.model_copy(update={"entry_snap_m": 77.0})})
    assert job_hash(moved) == job_hash(old), "the reach of a snap is no part of a job that leaves nothing out"
    on = valley_job(tmp_path, True)
    assert job_hash(on) != job_hash(old)
    with RasterBed(old.terrain.dem, old.terrain.pixel_stride) as bed:
        window = grid_window(old, bed)
        mask = np.ones((window.ny, window.nx), bool)
        assert grid_key(on, bed, window) == grid_key(old, bed, window), "the key moves with the cells, not the tick"
        assert grid_key(on, bed, window, left_out=~mask) != grid_key(old, bed, window)
        assert strip_key(on, bed, window, mask) == strip_key(old, bed, window, mask)


def test_the_outline_along_a_left_out_catchment_is_no_edge_for_the_stream_check(tmp_path) -> None:
    from tests.engine.test_edge_valleys import CRS, SIDE
    from tests.engine.test_edge_valleys import MID as VALLEY_MID
    from tests.engine.test_edge_valleys import valley as cut_ground
    from tests.engine.test_edge_valleys import valley_job as cut_valley
    from wadi2d.edge_valleys import stream_crossings

    cfg = cut_valley(cut_ground(tmp_path), 0.0, 1500.0)
    found = stream_crossings(cfg, CRS)
    assert [c.kind for c in found] == ["stream leaves"]
    around = shapely.Point(found[0].x, found[0].y).buffer(200.0)
    assert stream_crossings(cfg, CRS, None, around) == []
    elsewhere = shapely.Point(found[0].x + 0.4 * SIDE, VALLEY_MID).buffer(50.0)
    assert stream_crossings(cfg, CRS, None, elsewhere) == found


def test_the_snap_reads_only_the_catchments_its_entry_brings_in(tmp_path) -> None:
    cfg = valley_job(tmp_path, True, entry=INSIDE)
    tables, _crs = prepare_grid(cfg, tmp_path / "cache")
    other = shapely.Polygon(ring(X0 + 300.0, X0 + 320.0))
    left = LeftOut({"Up": "In", "Far": "Other"}, {"Up": tables.left_out.polygons["Up"], "Far": other})
    (snap,) = snap_entries(cfg, tables, [("In", INSIDE, None, None)], left)
    assert snap.point[0] == EDGE + DX / 2.0, "not the lower cell beside the other catchment, 150 m down the wadi"
    assert left.entries == [snap.point] and left.entry_cells(tables.grid).sum() == 1


def thalweg_file(tmp_path, y: float = MID - 1.0):
    """A Suggest file with one thalweg down the whole valley, through the catchment and the grid below it."""
    import fiona

    path = tmp_path / "suggest.gpkg"
    schema = {"geometry": "LineString", "properties": {"area_km2": "float", "incised_m": "float"}}
    with fiona.open(path, "w", driver="GPKG", layer="thalwegs", schema=schema, crs="EPSG:32640") as dst:
        line_ = {"type": "LineString", "coordinates": [(X0 + 20.0, y), (X0 + 364.0, y)]}
        dst.write({"geometry": line_, "properties": {"area_km2": 5.0, "incised_m": 2.0}})
    return path


def aligned(tmp_path) -> dict:
    return {"enabled": True, "generator": "centres", "banks": str(thalweg_file(tmp_path))}


def strip_cells(tables) -> tuple[np.ndarray, np.ndarray]:
    mesh = tables.strip.mesh
    return mesh.cx[: mesh.real], mesh.cy[: mesh.real]


def test_the_aligned_mesh_ends_at_the_catchments_edge(tmp_path) -> None:
    cut, _crs = prepare_grid(valley_job(tmp_path, True, strips=aligned(tmp_path)), tmp_path / "cache_cut")
    full, _crs = prepare_grid(valley_job(tmp_path, False, strips=aligned(tmp_path)), tmp_path / "cache_full")
    x_cut, _y = strip_cells(cut)
    x_full, _y = strip_cells(full)
    assert x_full.min() < EDGE - 100.0, "the line runs through the catchment: the full domain has cells on it there"
    assert x_cut.size > 100 and x_cut.min() > EDGE, "no aligned cell under the left-out catchment"
    assert x_cut.min() < EDGE + 2.0 * DX, "and the strip runs up to its edge"
    masked = np.zeros(cut.grid.shape, bool)
    masked[cut.strip.strip.masked] = True
    out = cut.left_out.on(cut.grid)
    assert not (masked & out).any() and not (cut.grid.mask & out).any()
    area, _cx, _cy = cut.strip.strip.geometry.areas_centroids()
    assert float(area.sum()) == pytest.approx(masked.sum() * DX * DX, rel=1e-9), "the cells tile the squares they replace"
    again, _crs = prepare_grid(valley_job(tmp_path, True, strips=aligned(tmp_path)), tmp_path / "cache_cut")
    assert np.array_equal(strip_cells(again)[0], x_cut), "from the strip cache, the same strip"
    assert again.left_out.names == ("Up",)


def test_the_aligned_run_without_the_catchment_closes_and_reads_the_full_domains_outflow(tmp_path) -> None:
    strips = aligned(tmp_path)
    full = run_job(valley_job(tmp_path, False, strips=strips), tmp_path / "full")
    cut = run_job(valley_job(tmp_path, True, strips=strips, entry=INSIDE), tmp_path / "cut")
    assert full.exit_code == 0 and cut.exit_code == 0, (full.message, cut.message)
    assert abs(cut.balance.relative) < 1e-6 and abs(full.balance.relative) < 1e-6
    assert cut.balance.inflow == pytest.approx(full.balance.inflow, rel=1e-6)
    assert cut.balance.rain == pytest.approx(full.balance.rain, rel=0.01), "the same ground is rained on, to a cell's edge"
    assert cut.balance.outflow == pytest.approx(full.balance.outflow, rel=0.01)
    q_cut, q_full = line(tmp_path / "cut")[1], line(tmp_path / "full")[1]
    assert np.abs(q_cut).max() == pytest.approx(np.abs(q_full).max(), rel=0.03)
    (record,) = json.loads((tmp_path / "cut" / "entries.json").read_text(encoding="utf-8"))
    assert EDGE < record["point"][0] < EDGE + 2.0 * DX and abs(record["point"][1] - MID) < 2.0 * DX


def test_the_estimate_and_the_mesh_preview_count_the_cells_that_are_left(tmp_path, capsys) -> None:
    from wadi2d.engine.cli import main
    from wadi2d.engine.estimate import estimate

    assert estimate(valley_job(tmp_path, True), "cpu").cells == estimate(valley_job(tmp_path, False), "cpu").cells - 40 * NY
    mesh = {"enabled": True, "min_dx": DX, "coarse_dx": 2.0 * DX, "analysis_pixel": DX}
    counts = {}
    for exclude in (False, True):
        path = tmp_path / f"job_{exclude}.json"
        path.write_text(valley_job(tmp_path, exclude, mesh=mesh).model_dump_json(), encoding="utf-8")
        assert main(["mesh", str(path), "--out", str(tmp_path / f"preview_{exclude}")]) == 0
        counts[exclude] = json.loads(capsys.readouterr().out.strip().splitlines()[-1])["cells"]
    assert 0 < counts[True] < counts[False]


def test_the_quadtree_leaves_the_catchment_out_too(tmp_path) -> None:
    mesh = {"enabled": True, "min_dx": DX, "coarse_dx": 2.0 * DX, "analysis_pixel": DX}
    cut = run_job(valley_job(tmp_path, True, mesh=mesh, entry=INSIDE), tmp_path / "cut")
    full = run_job(valley_job(tmp_path, False, mesh=mesh), tmp_path / "full")
    assert cut.exit_code == 0 and full.exit_code == 0, (cut.message, full.message)
    assert cut.cells < full.cells
    assert abs(cut.balance.relative) < 1e-6
    assert cut.balance.inflow == pytest.approx(full.balance.inflow, rel=1e-6)
    assert cut.balance.outflow == pytest.approx(full.balance.outflow, rel=0.01)
    (said,) = [e for e in events(tmp_path / "cut") if e.get("ev") == "left_out"]
    assert said["cells"] == 40 * NY
