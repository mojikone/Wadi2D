"""Pixel depth reads the modified terrain: on the raw DEM a cut channel would be dry and a dyke under water."""

from __future__ import annotations

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, job, write_dem
from tests.engine.test_earthworks_solver import (
    BOTTOM,
    DX,
    DYKE_TOP,
    FLOW,
    PIXEL,
    SIDE,
    TOP,
    N,
    S,
    normal_depth,
)
from wadi2d.products import runner, step
from wadi2d.products.step import PIXEL_DIR
from wadi2d.run import run_job

LENGTH, HEIGHT = 1080.0, 96.0
CREST_OFFSET = BOTTOM / 2.0 + SIDE * DYKE_TOP
"""From the centre line to the inner edge of the dyke's top, m."""


def straight_case(tmp_path, kind: str, depth_below_ground: float) -> tuple:
    nx, ny = round(LENGTH / PIXEL), round(HEIGHT / PIXEL)
    px = (np.arange(nx) + 0.5) * PIXEL
    ground = np.tile(TOP - S * px, (ny, 1))
    dem = write_dem(tmp_path / "plane.tif", ground, PIXEL)
    bed0 = TOP - depth_below_ground
    start, end = (X0, Y0 - HEIGHT / 2.0), (X0 + LENGTH, Y0 - HEIGHT / 2.0)
    if kind == "channel":
        shape = {
            "kind": "channel",
            "coordinates": [start, end],
            "z": [bed0, bed0 - S * LENGTH],
            "section": {"width": BOTTOM, "left_slope": SIDE, "right_slope": SIDE},
        }
    else:
        rows = [
            {"station": 0.0, "bed_z": bed0, "crest_z": bed0 + DYKE_TOP},
            {"station": LENGTH, "bed_z": bed0 - S * LENGTH, "crest_z": bed0 - S * LENGTH + DYKE_TOP},
        ]
        shape = {
            "kind": "channel_dyke",
            "coordinates": [start, end],
            "section": {"width": BOTTOM, "left_slope": SIDE, "right_slope": SIDE, "rows": rows},
        }
    stop = LENGTH - 60.0
    held = bed0 - S * stop + normal_depth(FLOW, BOTTOM, SIDE, N, S)
    cfg = job(
        dem,
        nx // 4,
        ny // 4,
        DX,
        terrain={"objects": [shape], "manning": N},
        hydrology={
            "inflows": [
                {"name": "in", "x": X0 + 60.0, "y": start[1], "times_s": [0.0, 1e6], "flows": [FLOW, FLOW]}
            ],
            "inject_radius": 10.0,
        },
        boundaries=[
            # between the dykes only: wider, the held level would flood the land behind them
            {"kind": "stage", "coordinates": [(X0 + stop, start[1] - 8.0), (X0 + stop, start[1] + 8.0)], "stage": held}
        ],
        run={"duration_s": 2400.0, "source_every_s": 30.0},
        outputs={"map_every_s": 600.0},
    )
    summary = run_job(cfg, tmp_path / "run")
    assert summary.exit_code == 0, summary.message
    assert summary.products == runner.PRODUCTS_DONE
    with rasterio.open(tmp_path / "run" / PIXEL_DIR / step.DEPTH_FILE) as src:
        depth = src.read(1, masked=True).filled(0.0)
        t = src.transform
    x = t.c + (np.arange(depth.shape[1]) + 0.5) * t.a
    y = t.f + (np.arange(depth.shape[0]) + 0.5) * t.e
    reach = (x > X0 + 0.4 * LENGTH) & (x < X0 + 0.7 * LENGTH)
    return depth[:, reach], np.abs(y - start[1])


def test_a_cut_channel_reads_its_depth_where_the_raw_dem_stands_above_the_water(tmp_path) -> None:
    depth, off = straight_case(tmp_path, "channel", 3.0)
    expected = normal_depth(FLOW, BOTTOM, SIDE, N, S)
    assert expected < 3.0  # the water never reaches the old ground: on the raw DEM every pixel would be dry
    assert np.median(depth[off < 3.0]) == pytest.approx(expected, rel=0.08)


def test_a_dyke_stands_dry_though_the_water_is_above_the_old_ground(tmp_path) -> None:
    depth, off = straight_case(tmp_path, "channel_dyke", 0.5)
    expected = normal_depth(FLOW, BOTTOM, SIDE, N, S)
    assert expected > 0.5  # on the raw DEM the water would lie over the dyke and past it
    assert np.median(depth[off < 3.0]) == pytest.approx(expected, rel=0.08)
    edge = BOTTOM / 2.0 + SIDE * expected  # where the surface meets the dyke's inner slope
    wet_to = off[(depth >= 0.05).any(axis=1)].max()
    assert wet_to == pytest.approx(edge, abs=1.0)
    assert wet_to < CREST_OFFSET
