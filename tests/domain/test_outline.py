"""The domain completed from a drawn outline (W97), on two valleys known without any delineation.

Two V valleys run south to a sea (no ground south of SEA_ROW), split by a ridge; outer ridges close them west and east,
and a ridge at HEAD_ROW closes them north, beyond which the ground falls to the DEM's north edge. So valley A's
catchment is the rectangle of columns A_WEST..A_EAST and rows HEAD_ROW + 1 .. SEA_ROW - 1, and every test knows it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
import shapely
from rasterio.transform import Affine

from wadi2d.config.schema import BasinSettings, DomainSettings
from wadi2d.domain.outline import ADDED, NOT_ADDED, REMOVED, complete_outline, kept_lines
from wadi2d.run import load_job

pytest.importorskip("whitebox")

PIXEL = 10.0
NY, NX = 300, 200
X0, Y0 = 500_000.0, 2_500_000.0
CRS = "EPSG:32640"
BED, BED_SLOPE, SIDE_SLOPE, NORTH_FALL = 100.0, 0.02, 0.05, 0.03
AXES = (-31, 60, 151, 242)
"""Valley axes by column; the two off the DEM make the outer ridges, half a pixel off a column so no pixel ties."""
SEA_ROW, HEAD_ROW = 280, 40
A_WEST, A_EAST = 15, 105
"""Valley A's catchment by column, inclusive: the ridges lie half-way between its axis and its neighbours'."""
THRESHOLD = BasinSettings(stream_threshold_km2=0.1)
CORNER = 1e-6
"""Exact, the corners too: where a rough edge meets the kept sea edge, the last row steps over the rough edge within half
a pixel of the sea edge's end, and the rough edge, nearer, is the one it crosses."""


def x_at(col: float) -> float:
    return X0 + col * PIXEL


def y_at(row: float) -> float:
    return Y0 - row * PIXEL


def ground() -> np.ndarray:
    rows, cols = np.mgrid[0:NY, 0:NX]
    along = np.where(
        rows >= HEAD_ROW,
        BED + (NY - rows) * PIXEL * BED_SLOPE,
        BED + (NY - HEAD_ROW) * PIXEL * BED_SLOPE - (HEAD_ROW - rows) * PIXEL * NORTH_FALL,
    )
    across = np.min(np.abs(cols[..., None] - np.array(AXES)), axis=-1) * PIXEL * SIDE_SLOPE
    z = along + across
    z[rows >= SEA_ROW] = -9999.0
    return z


def box(c0: float, r0: float, c1: float, r1: float) -> shapely.Polygon:
    """Columns c0..c1 and rows r0..r1 as edges of the pixel lattice."""
    return shapely.box(x_at(c0), y_at(r1), x_at(c1), y_at(r0))


CATCHMENT_A = box(A_WEST, HEAD_ROW + 1, A_EAST + 1, SEA_ROW)
SEA = [(x_at(0), y_at(SEA_ROW)), (x_at(NX), y_at(SEA_ROW))]


def _geojson(path: Path, geometry: shapely.Geometry) -> Path:
    feature = {"type": "Feature", "properties": {}, "geometry": shapely.geometry.mapping(geometry)}
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
    return path


def make_job(folder: Path, outline: shapely.Geometry, boundaries: list | None = None) -> Path:
    dem = folder / "dem.tif"
    with rasterio.open(dem, "w", driver="GTiff", height=NY, width=NX, count=1, dtype="float32", nodata=-9999.0,
                       crs=CRS, transform=Affine(PIXEL, 0.0, X0, 0.0, -PIXEL, Y0)) as dst:  # fmt: skip
        dst.write(ground().astype(np.float32), 1)
    job = {
        "grid": {"dx": 20.0, "domain": str(_geojson(folder / "outline.geojson", outline))},
        "mesh": {"analysis_pixel": PIXEL},
        "terrain": {"dem": str(dem)},
        "boundaries": boundaries if boundaries is not None else [{"kind": "normal", "coordinates": SEA}],
        "basin": {"stream_threshold_km2": 0.1},
    }
    path = folder / "job.json"
    path.write_text(json.dumps(job), encoding="utf-8")
    return path


ROUGH = box(25, 150, 111, SEA_ROW)
"""Valley A drawn roughly: 10 columns short of its west ridge, 5 over its east ridge into valley B, cut at row 150, and
exactly on the sea."""


def complete(job: Path, **settings):
    cfg = load_job(job)
    outline = shapely.union_all([ROUGH])
    return complete_outline(cfg, outline, kept_lines(cfg, None), THRESHOLD, DomainSettings(**settings))


def test_a_cut_catchment_is_completed_and_the_overreach_cut(tmp_path: Path) -> None:
    done = complete(make_job(tmp_path, ROUGH))
    assert done.polygon.symmetric_difference(CATCHMENT_A).area <= CORNER
    r = done.report
    # columns 106 to 110, rows 150 to 279
    assert r["removed_km2"] == pytest.approx(5 * 130 * PIXEL**2 / 1e6)
    added = (CATCHMENT_A.area - CATCHMENT_A.intersection(ROUGH).area) / 1e6
    assert r["added_km2"] == pytest.approx(added)
    assert (
        len(r["catchments_added"]) == 1 and r["catchments_added"][0]["km2"] > 0.1
    )  # the valley above row 150
    assert (
        r["catchments_removed"] == [] and r["slivers_removed_km2"] > 0.0
    )  # valley B's slope, under the threshold
    kinds = {c.kind for c in done.changes}
    assert kinds == {ADDED, REMOVED}


def test_without_kept_lines_nothing_is_cut(tmp_path: Path) -> None:
    done = complete(make_job(tmp_path, ROUGH, boundaries=[]))
    assert done.report["removed_km2"] == 0.0
    assert done.polygon.symmetric_difference(CATCHMENT_A.union(ROUGH)).area < 1e-6


def test_water_arriving_across_a_kept_edge_stays_outside(tmp_path: Path) -> None:
    north = [(x_at(0), y_at(150)), (x_at(NX), y_at(150))]
    job = make_job(
        tmp_path, ROUGH, [{"kind": "normal", "coordinates": SEA}, {"kind": "normal", "coordinates": north}]
    )
    done = complete(job)
    assert done.polygon.bounds[3] == pytest.approx(y_at(150))  # the north edge stays as drawn
    assert done.report["catchments_not_added"] and any("needs an inflow" in n for n in done.report["notes"])
    assert NOT_ADDED in {c.kind for c in done.changes}


def test_the_window_widens_until_the_catchment_is_whole(tmp_path: Path) -> None:
    done = complete(make_job(tmp_path, ROUGH), margin_m=100.0)
    assert done.report["window"]["widened"] >= 1
    assert done.polygon.symmetric_difference(CATCHMENT_A).area <= CORNER


def test_the_command_writes_the_domain(tmp_path: Path) -> None:
    from wadi2d.engine.cli import main
    from wadi2d.io.geopackage import layer_names
    from wadi2d.terrain.vector import read_features

    job = make_job(tmp_path, ROUGH)
    assert main(["domain", str(job), "--out", str(tmp_path / "out"), "--threshold-km2", "0.1"]) == 0
    ((_p, polygon),) = read_features(tmp_path / "out" / "domain.geojson")
    assert polygon.symmetric_difference(CATCHMENT_A).area <= CORNER
    assert set(layer_names(tmp_path / "out" / "domain.gpkg")) >= {"domain", "changes"}
    report = json.loads((tmp_path / "out" / "domain_report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "complete" and report["stream_threshold_km2"] == 0.1
