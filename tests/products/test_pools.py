"""A dam's pool on the grid as an element of record (W106, gap 8 of W104): the held side behind its line, and the
inflow by the pool's balance."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from wadi2d.products.pools import PIXEL_M, PART, WIDEN_M, _balance, _pool_mask


def _valley(path, size=1200):
    """A valley falling south at 1 %, side slopes 5 %, 5 m pixels, west edge 0, north edge 10,000."""
    y = 10000.0 - (np.arange(size) + 0.5) * PIXEL_M
    x = (np.arange(size) + 0.5) * PIXEL_M
    z = 100.0 + 0.01 * (y[:, None] - 4000.0) + 0.05 * np.abs(x[None, :] - 3000.0)
    with rasterio.open(path, "w", driver="GTiff", height=size, width=size, count=1, dtype="float32",
                       crs="EPSG:32640", transform=Affine(PIXEL_M, 0.0, 0.0, 0.0, -PIXEL_M, 10000.0)) as dst:  # fmt: skip
        dst.write(z.astype(np.float32), 1)
    return z


def test_the_pool_is_the_held_side_behind_the_dam(tmp_path) -> None:
    dem = tmp_path / "dem.tif"
    z = _valley(dem)

    def read(x0, y0, ny, nx):
        col, row = int(round(x0 / PIXEL_M)), int(round((10000.0 - y0) / PIXEL_M))
        out = np.full((ny, nx), np.nan)
        part = z[row : row + ny, col : col + nx]
        out[: part.shape[0], : part.shape[1]] = part
        return out

    dam = SimpleNamespace(coordinates=[(2000.0, 5000.0), (4000.0, 5000.0)])  # across the valley at y 5,000: bed 110 m
    mask, (x0, y0, pixel) = _pool_mask(read, str(dem), [dam], 115.0)
    def at(x, y):
        return bool(mask[int((y0 - y) / pixel), int((x - x0) / pixel)])
    assert at(3000.0, 5100.0) and at(3000.0, 5450.0)  # the pool: the bed under 115 m up to y 5,500
    assert not at(3000.0, 5600.0 + WIDEN_M)  # above the level and the widening
    assert at(3000.0, 4980.0) and not at(3000.0, 4800.0)  # below the dam only the widening's 60 m
    assert PART.sub("", "Bidah 03 part 2") == "Bidah 03"


def test_the_inflow_is_the_change_of_the_water_plus_what_left() -> None:
    t = np.array([0.0, 900.0, 1800.0])
    storage = np.array([0.0, 90000.0, 135000.0])
    line = (np.array([0.0, 900.0, 1800.0]), np.array([0.0, 0.0, 20.0]))
    ends, inflow, outflow = _balance(t, storage, line)
    assert list(ends) == [900.0, 1800.0]
    assert inflow == pytest.approx([100.0, (45000.0 + 9000.0) / 900.0]) and outflow == pytest.approx([0.0, 10.0])


def test_a_pool_is_made_for_a_dam_not_for_any_crest_line() -> None:
    """A named crest line with a spillway on it, or a result line of its name, is a dam; a road or Suggest's crests
    are not (the older dock scenarios' runs slowed by a pool search on every crest line)."""
    from wadi2d.config.schema import RunConfig
    from wadi2d.products.pools import _dams

    def crest(name, x0, y0=0.0):
        return {"kind": "crest_line", "name": name, "coordinates": [[x0, y0], [x0 + 200.0, y0]], "z_constant": 110.0}

    cfg = RunConfig.model_validate({
        "terrain": {"dem": "x.tif", "objects": [
            crest("Dam A", 0.0), crest("Dam A part 2", 300.0),
            {"kind": "spillway", "name": "Dam A spillway", "coordinates": [[50.0, 0.0], [120.0, 0.0]], "z_constant": 105.0,
             "coefficient": 2.1, "length": 70.0},
            crest("Road", 5000.0), crest("Dyke B", 9000.0),
        ]},
        "outputs": {"lines": [{"name": "Dyke B", "coordinates": [[9000.0, 0.0], [9200.0, 0.0]]}]},
    })  # fmt: skip
    dams = _dams(cfg)
    assert set(dams) == {"Dam A", "Dyke B"} and len(dams["Dam A"]) == 2
