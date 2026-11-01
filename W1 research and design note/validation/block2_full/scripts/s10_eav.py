"""Reservoir volume against elevation: the model's tables, a pixel flood-fill of the same DEM, and the EAV csv.

Levels are on the EAV's datum (NSA). The GGC terrain sits 2.39 m higher, so its levels are shifted by that much.
Model: cells reached from the lowest cell of the reservoir polygon through faces whose invert lies below the level,
faces carrying a terrain object closed; volume through the solver's own table (hbar_at_level).
Flood-fill: DEM pixels at 2 m, connected below the level, crest lines as barriers.
"""
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
import rasterio
import rasterio.features
import shapefile
import shapely
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from scipy import ndimage

sys.path.insert(0, r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\block2_full\scripts")
from common import CACHE, DAMS, DEM, OUT
from dams import DAM_LIST, GGC_MINUS_NSA, NSA2
from dams import job as dam_job

from wadi2d.config.schema import RunConfig
from wadi2d.run import prepare_grid
from wadi2d.solver.layout import CLOSED
from wadi2d.tables import hbar_at_level
from wadi2d.terrain import apply_objects

_shapes = [shapely.geometry.shape(s.__geo_interface__) for s in shapefile.Reader(str(DAMS / "Reservoirs.shp")).shapes()]
RES = {"Bidah 03": _shapes[0], "Faydh 01": _shapes[1]}


def connected(tables, seed, level, xclosed, yclosed):
    grid = tables.grid
    zmin = tables.zmin
    fl_x = grid.from_tiles(tables.flx)
    fl_y = grid.from_tiles(tables.fly)
    ny, nx = grid.shape
    seen = np.zeros((ny, nx), bool)
    if zmin[seed] >= level:
        return seen
    seen[seed] = True
    q = deque([seed])
    while q:
        j, i = q.popleft()
        for a, b, fj, fi, f, closed, nl in ((j, i + 1, j, i + 1, fl_x, xclosed, (j, i)), (j, i - 1, j, i, fl_x, xclosed, (j, i - 1)),
                                            (j + 1, i, j + 1, i, fl_y, yclosed, (j, i)), (j - 1, i, j, i, fl_y, yclosed, (j - 1, i))):
            if not (0 <= a < ny and 0 <= b < nx) or seen[a, b] or not grid.mask[a, b]:
                continue
            v = f[fj, fi]
            if closed[fj, fi] or v >= CLOSED * 0.5:
                continue
            if zmin[nl] + v < level:
                seen[a, b] = True
                q.append((a, b))
    return seen


def lowest_cell(tables, poly):
    grid = tables.grid
    jj, ii = np.nonzero(grid.mask)
    x, y = grid.xy_of(jj, ii)
    inside = shapely.contains_xy(poly.buffer(-45.0), x, y)
    jj, ii = jj[inside], ii[inside]
    k = int(np.argmin(tables.zmin[jj, ii]))
    return int(jj[k]), int(ii[k])


def fill_curve(dam, levels, dem, stride):
    b = dam_box(dam)
    with rasterio.open(dem) as src:
        w = from_bounds(*b, src.transform).round_offsets().round_lengths()
        h, wd = int(w.height // stride), int(w.width // stride)
        w = rasterio.windows.Window(w.col_off, w.row_off, wd * stride, h * stride)
        z = src.read(1, window=w, out_shape=(h, wd), resampling=Resampling.nearest, masked=True).astype(np.float64).filled(np.nan)
        t0 = src.window_transform(w)
        pix = src.res[0] * stride
    t = from_origin(t0.c, t0.f, pix, pix)
    lines = [shapely.LineString(c) for c in dam.crest_lines]
    barrier = rasterio.features.rasterize(lines, out_shape=z.shape, transform=t, fill=0, default_value=1, all_touched=True, dtype="uint8").astype(bool)
    barrier = ndimage.binary_dilation(barrier, structure=np.ones((3, 3)))
    inside = rasterio.features.geometry_mask([RES[dam.name].buffer(-45.0)], z.shape, t, invert=True)
    row, col = np.unravel_index(int(np.nanargmin(np.where(inside, z, np.nan))), z.shape)
    out = []
    for lv in levels:
        wet = (z < lv) & ~barrier
        lab, _ = ndimage.label(wet)
        k = lab[row, col]
        m = lab == k if k > 0 else np.zeros_like(wet)
        out.append((float(m.sum() * pix * pix), float(((lv - z)[m]).sum() * pix * pix)))
    return out


def dam_box(dam):
    if dam.name.startswith("Bidah"):
        return (435500.0, 2724500.0, 439000.0, 2727800.0)
    return (427500.0, 2730500.0, 431500.0, 2735000.0)


def curve(dam, dx, dem, shift, stride):
    t = np.array([0.0, 3600.0])
    q = np.array([0.0, 0.0])
    j = dam_job(dam, f"eav_{dam.name}_{dx}", dx, t, q, 3600.0, dem=dem, shift=shift)
    cfg = RunConfig.model_validate(j)
    tables, _ = prepare_grid(cfg, Path(CACHE))
    grid = tables.grid
    pixel = float(dx / round(dx / (rasterio.open(dem).res[0] * cfg.terrain.pixel_stride)))
    crest = apply_objects(grid, cfg.terrain.objects, pixel).crest
    xclosed, yclosed = np.isfinite(crest.xz), np.isfinite(crest.yz)
    hc = grid.from_tiles(tables.hc)
    dtab = grid.from_tiles(tables.dtab)
    levels = np.arange(dam.fsl - 12.0, dam.crest + 2.01, 1.0)
    e = dam.eav()
    fill = fill_curve(dam, levels + shift, dem, stride)
    seed = lowest_cell(tables, RES[dam.name])
    rows = []
    for lv, (af, vf) in zip(levels, fill, strict=True):
        m = connected(tables, seed, lv + shift, xclosed, yclosed)
        h = np.asarray(hbar_at_level(lv + shift, tables.zmin[m], hc[m], dtab[m]))
        rows.append({"z": float(lv), "eav_V": float(np.interp(lv, e[:, 1], e[:, 2])), "eav_A": float(np.interp(lv, e[:, 1], e[:, 0])),
                     "model_V": float(h.sum() * dx * dx), "fill_V": vf, "fill_A": af})
    return rows


if __name__ == "__main__":
    res = {}
    for dam in DAM_LIST.values():
        for label, dem, shift, stride in (("NSA 2 m", NSA2, 0.0, 1), ("GGC 0.5 m shifted", DEM, GGC_MINUS_NSA, 4)):
            for dx in (20.0, 10.0):
                rows = curve(dam, dx, dem, shift, stride)
                res[f"{dam.name} | {label} | {dx:g}"] = rows
                print(dam.name, label, dx)
                for r in rows[::3] + rows[-5:-2:2]:
                    print(f"  z {r['z']:6.1f} EAV {r['eav_V']/1e6:7.3f} | model {r['model_V']/1e6:7.3f} ratio {r['model_V']/max(r['eav_V'],1):.3f} | fill {r['fill_V']/1e6:7.3f} A {r['fill_A']/1e6:6.3f} ratio {r['fill_V']/max(r['eav_V'],1):.3f}")
    (OUT / "eav_check.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
