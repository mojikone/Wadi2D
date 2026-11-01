"""The engine on the real Block 2 files, read-only: rasters, polygons, HMS network, accumulation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio

from wadi2d.arf import accumulation_on_grid
from wadi2d.config.schema import RunConfig
from wadi2d.forcing import _labels, build_storm, load_polygons
from wadi2d.grid import TileGrid
from wadi2d.run import hydrographs
from wadi2d.terrain import RasterBed

pytestmark = pytest.mark.data

BIDAH = (438500.0, 2727000.0)
WINDOW = (438200.0, 2726700.0, 438900.0, 2727300.0)
"""Around the Bidah 03 dam line."""


@pytest.fixture(scope="module")
def terrain(block2_dir: Path) -> Path:
    return block2_dir / "Hydrology" / "Terrain"


def test_the_27_gb_raster_reads_by_windows(terrain: Path):
    with (
        RasterBed(terrain / "GGC_2_MERGE_HDSM.tif") as fine,
        RasterBed(terrain / "GGC_2_MERGE_HDSM_5.tif") as coarse,
    ):
        assert fine.pixel == 0.5
        assert coarse.pixel == 5.0
        w = coarse.snap((BIDAH[0], BIDAH[1], BIDAH[0] + 100.0, BIDAH[1] + 100.0), 20.0)
        fine.bind(w.x0, w.y0)
        coarse.bind(w.x0, w.y0)
        a = fine.read(0, 0, 640, 640)
        b = coarse.read(0, 0, 64, 64)
        assert np.isfinite(a).all()
        assert a.shape == (640, 640)
        assert a[5:635, 5:635].mean() == pytest.approx(b[1:63, 1:63].mean(), abs=1.0)


def test_pixel_stride_on_the_fine_raster(terrain: Path):
    with RasterBed(terrain / "GGC_2_MERGE_HDSM.tif", pixel_stride=4) as bed:
        assert bed.pixels_per_cell(20.0) == 10
        with pytest.raises(ValueError, match="not a multiple"):
            bed.pixels_per_cell(25.0)
        w = bed.snap((BIDAH[0], BIDAH[1], BIDAH[0] + 100.0, BIDAH[1] + 100.0), 20.0)
        bed.bind(w.x0, w.y0)
        assert bed.read(0, 0, 32, 32).shape == (32, 32)


def test_nodata_at_the_sea_is_inactive(terrain: Path):
    with RasterBed(terrain / "GGC_2_MERGE_HDSM_5.tif") as bed:
        w = bed.snap((436000.0, 2740000.0, 452000.0, 2746000.0), 40.0)
        mask = bed.active_mask(w, 40.0)
    assert mask.any()
    assert not mask.all()


def test_subbasin_polygons_rasterise_to_their_areas(hms_project_dir: Path):
    cfg = RunConfig.model_validate({"hydrology": {"hms_sqlite": str(hms_project_dir / "Basin_1.sqlite")}})
    polygons = load_polygons(cfg.hydrology)
    assert len(polygons) == 18
    grid = TileGrid.from_mask(np.ones((3000, 3000), bool), 415000.0, 2740000.0, 10.0)
    cells = int(np.count_nonzero(_labels(grid, [polygons["S13"]])))
    assert cells * 100.0 * 1e-6 == pytest.approx(20.971, rel=0.005)


def test_lumped_hydrograph_comes_from_the_hms_basin(hms_project_dir: Path):
    cfg = RunConfig.model_validate(
        {
            "storm": {"kind": "uniform", "depth_mm": 100.0, "duration_min": 120.0},
            "hydrology": {
                "hms_basin": str(hms_project_dir / "Basin_1.basin"),
                "subbasins": [{"name": "S13", "mode": "lumped", "outlet": BIDAH}],
                "inflows": [{"name": "Faydh", "x": 431000.0, "y": 2733700.0, "element": "Faydh 01"}],
            },
            "run": {"duration_s": 86400.0},
        }
    )
    flows = hydrographs(cfg, build_storm(cfg))
    assert {f[0] for f in flows} == {"S13", "Faydh"}
    for name, _point, times, q in flows:
        volume = np.trapezoid(q, times)
        area = 20.971 if name == "S13" else 74.304
        assert volume / (area * 1e6) * 1000.0 == pytest.approx(70.0, abs=25.0), name


def test_accumulation_raster_gives_the_dam_catchment(hms_project_dir: Path, terrain: Path):
    raster = hms_project_dir / "terrain" / "GGC_2_MERGE_HDSM_5m" / "00" / "flowaccum.tif"
    with rasterio.open(raster) as src:
        left, top = src.bounds.left, src.bounds.top
    dx = 20.0
    x0 = left + round((WINDOW[0] - left) / 5.0) * 5.0
    y0 = top - round((top - WINDOW[3]) / 5.0) * 5.0
    ny, nx = int((WINDOW[3] - WINDOW[1]) / dx), int((WINDOW[2] - WINDOW[0]) / dx)
    grid = TileGrid.from_mask(np.ones((ny, nx), bool), x0, y0, dx)
    area = accumulation_on_grid(str(raster), "cells", grid)
    assert area.max() == pytest.approx(20.97, rel=0.1)
    assert np.median(area[grid.mask]) < 1.0
