"""The smooth drawing: edges move little, areas hold, classes neither overlap nor leave gaps, nothing invents water."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys

import numpy as np
import pytest
import rasterio
import shapely
from scipy import ndimage

from wadi2d.config.schema import RunConfig
from wadi2d.grid.tiles import TileGrid
from wadi2d.io.geopackage import write_geopackage
from wadi2d.io.geotiff import raster_profile
from wadi2d.products import smooth as sm
from wadi2d.products.smooth_geometry import chaikin
from wadi2d.products.step import Watch

PIXEL = 5.0
X0, Y0 = 400000.0, 2700000.0
CFG = RunConfig()


def calm() -> Watch:
    return Watch(lambda *_a, **_k: None, lambda: False)


def rough_classes(n: int = 600, seed: int = 5) -> np.ndarray:
    """Classes from a noisy field: patches, thin strips and holes, like the real thing."""
    noise = ndimage.gaussian_filter(np.random.default_rng(seed).normal(size=(n, n)), 12.0)
    noise = noise / noise.std()
    return np.digitize(noise, [-0.2, 0.2, 0.5, 0.8, 1.1, 1.5]).astype(np.uint8)


def profile_of(classes: np.ndarray) -> dict:
    return raster_profile(classes.shape, PIXEL, X0, Y0, "EPSG:32640")


def test_blocks_share_a_line_and_cover_everything() -> None:
    ranges = list(sm.block_ranges(10, 4))
    assert ranges == [(-1, 3), (3, 7), (7, 10)]


def test_window_reads_off_the_array_as_fill() -> None:
    a = np.arange(9).reshape(3, 3)
    out = sm.window(a, -1, 2, -1, 2, -5)
    assert out[0, 0] == -5 and out[1, 1] == 0 and out[2, 2] == 4


def test_speckle_goes_and_a_large_patch_stays() -> None:
    mask = np.zeros((60, 60), bool)
    mask[10:40, 10:40] = True
    mask[50, 50] = True
    mask[20, 20] = False
    clean = sm.despeck(mask, 5)
    assert not clean[50, 50]  # patch
    assert clean[20, 20]  # hole
    assert clean[15, 15]


def test_a_patch_at_the_window_edge_is_left_alone() -> None:
    mask = np.zeros((20, 20), bool)
    mask[0, 5] = True
    assert sm.despeck(mask, 5)[0, 5]


def test_the_contour_holds_the_area_it_is_asked_for() -> None:
    mask = rough_classes() >= 3
    field = sm.soft(mask, 1.0)
    level = sm.area_iso(field, int(mask.sum()))
    area = sum(p.area for p in sm.contour_polygons(field, level))
    assert area == pytest.approx(mask.sum(), rel=0.005)


def test_classes_keep_their_area_and_neither_overlap_nor_leave_gaps() -> None:
    classes = rough_classes()
    rows, accounts = sm.class_polygons(CFG, classes, profile_of(classes), calm())
    for name in ("H3", "H4", "H5", "H6"):
        assert abs(accounts["change_pct"][name]) < 1.0
    parts = [g for _k, _b, g in rows]
    together = shapely.union_all(parts)
    assert sum(p.area for p in parts) == pytest.approx(together.area, rel=1e-6)
    cover = shapely.MultiPolygon(
        [p for p in shapely.get_parts(shapely.make_valid(together)) if p.geom_type == "Polygon"]
    )
    wet = (classes > 0).sum() * PIXEL**2
    assert cover.area == pytest.approx(wet, rel=0.02)
    assert all(shapely.is_valid(p) for p in parts)


def test_an_edge_does_not_move_more_than_a_pixel_or_two() -> None:
    classes = rough_classes()
    _rows, accounts = sm.class_polygons(CFG, classes, profile_of(classes), calm())
    wet_km2 = (classes > 0).sum() * PIXEL**2 / 1e6
    assert accounts["wet_added_km2"] < 0.05 * wet_km2


def test_smooth_edges_are_not_a_staircase() -> None:
    """A diagonal strip drawn in pixels: a staircase turns through a right angle at every pixel; this does not."""
    n = 400
    down, across = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    classes = (np.abs(down - across) < 40).astype(np.uint8)
    rows, _ = sm.class_polygons(CFG, classes, profile_of(classes), calm())
    largest = max(shapely.get_parts(rows[0][2]), key=lambda part: part.area)
    ring = shapely.get_coordinates(largest.exterior)
    steps = np.diff(ring, axis=0)
    turns = np.abs(np.angle(np.exp(1j * np.diff(np.arctan2(steps[:, 1], steps[:, 0])))))
    assert (turns > np.radians(30.0)).sum() < 12  # the four ends of the strip, nothing along it


def test_the_block_size_does_not_change_the_areas() -> None:
    classes = rough_classes(800)
    small = RunConfig.model_validate({"outputs": {"smooth": {"block_px": 256}}})
    one = sm.class_polygons(CFG, classes, profile_of(classes), calm())[1]["drawn_km2"]
    many = sm.class_polygons(small, classes, profile_of(classes), calm())[1]["drawn_km2"]
    for name, area in one.items():
        assert many[name] == pytest.approx(area, abs=0.02 * max(area, 0.01))


def test_a_block_counts_its_edge_pixels_by_half() -> None:
    assert sm.block_area(np.ones((5, 5), bool)) == 16.0  # 4 x 4 pixel widths between the outer centres


def test_small_blocks_keep_the_classes_too() -> None:
    classes = rough_classes(900)
    small = RunConfig.model_validate({"outputs": {"smooth": {"block_px": 256}}})
    change = sm.class_polygons(small, classes, profile_of(classes), calm())[1]["change_pct"]
    for name in ("H3", "H4", "H5", "H6"):
        assert abs(change[name]) < 1.0


def test_a_stop_stops_the_polygons() -> None:
    from wadi2d.products.step import ProductsStopped

    classes = rough_classes(300)
    with pytest.raises(ProductsStopped):
        sm.class_polygons(CFG, classes, profile_of(classes), Watch(lambda *_a, **_k: None, lambda: True))


def test_depth_drawing_is_soft_at_the_edge_and_invents_nothing(tmp_path) -> None:
    depth = np.zeros((300, 300), np.float32)
    down, across = np.meshgrid(np.arange(300), np.arange(300), indexing="ij")
    depth[((down - 150) ** 2 + (across - 150) ** 2) < 100**2] = 2.0
    out = sm.depth_drawing(CFG, depth, profile_of(depth), tmp_path / "d.tif", calm())
    with rasterio.open(out) as src:
        drawn = src.read(1)
        assert src.transform.a == pytest.approx(PIXEL / CFG.outputs.smooth.depth_scale)
    scale = CFG.outputs.smooth.depth_scale
    far = ndimage.binary_dilation(depth > 0.0, iterations=5)
    outside = np.repeat(np.repeat(~far, scale, axis=0), scale, axis=1)
    assert drawn[outside].max() == 0.0
    assert drawn.max() == pytest.approx(2.0, abs=0.01)
    between = ((drawn > 0.05) & (drawn < 1.95)).sum()
    assert between > 100  # a soft edge, not a hard one
    area = (drawn > 1.0).sum() / scale**2
    assert area == pytest.approx((depth > 0.0).sum(), rel=0.01)


def test_chaikin_rounds_a_stair() -> None:
    ring = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0], [0.0, 0.0]])
    out = chaikin(ring, 2)
    assert out.shape[0] == 17
    assert np.array_equal(out[0], out[-1])
    assert shapely.Polygon(out).area < 4.0


def test_domain_outline_follows_the_cells_without_their_stairs() -> None:
    mask = np.zeros((96, 96), bool)
    down, across = np.meshgrid(np.arange(96), np.arange(96), indexing="ij")
    mask[np.abs(down - across) < 20] = True
    grid = TileGrid.from_mask(mask, X0, Y0, 20.0)

    class Tables:
        pass

    tables = Tables()
    tables.grid = grid
    outline = sm.domain_outline(tables, CFG.outputs.smooth.domain_sigma_cells)
    assert outline.area == pytest.approx(mask.sum() * 400.0, rel=0.03)
    ring = shapely.get_coordinates(shapely.get_parts(outline)[0].exterior)
    steps = np.diff(ring, axis=0)
    steps = steps[np.hypot(*steps.T) > 1e-6]
    turns = np.abs(np.angle(np.exp(1j * np.diff(np.arctan2(steps[:, 1], steps[:, 0])))))
    assert np.quantile(turns, 0.99) < np.radians(45.0)


def test_geopackage_is_read_by_gdal_with_both_layers(tmp_path) -> None:
    """GDAL in a process of its own: a second GDAL does not go in beside rasterio's."""
    classes = rough_classes(300)
    rows, _ = sm.class_polygons(CFG, classes, profile_of(classes), calm())
    domain = shapely.MultiPolygon([shapely.box(X0, Y0 - 100.0, X0 + 100.0, Y0)])
    wkt = rasterio.crs.CRS.from_epsg(32640).to_wkt()
    layers = sm.class_layers(rows, domain, ["H1", "H2", "H3", "H4", "H5", "H6"])
    path = write_geopackage(tmp_path / "h.gpkg", layers, wkt)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA application_id").fetchone()[0] == 0x47504B47
        assert db.execute("SELECT count(*) FROM hazard_classes").fetchone()[0] == len(rows)
    script = (
        "import json, sys, pyogrio\n"
        "layers = [str(row[0]) for row in pyogrio.list_layers(sys.argv[1])]\n"
        "info = pyogrio.read_info(sys.argv[1], layer='hazard_classes')\n"
        "print(json.dumps([layers, list(info['fields']), str(info['crs'])]))\n"
    )
    done = subprocess.run([sys.executable, "-c", script, str(path)], capture_output=True, text=True, check=False)
    if "No module named" in done.stderr:
        pytest.skip("no pyogrio here")
    assert done.returncode == 0, done.stderr
    layers, fields, crs = json.loads(done.stdout)
    assert set(layers) == {sm.CLASS_LAYER, sm.DOMAIN_LAYER}
    assert set(fields) >= {"class", "name", "area_km2"}
    assert "32640" in crs
