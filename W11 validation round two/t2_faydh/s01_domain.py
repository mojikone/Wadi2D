"""The domain of both models, and the terrain clip: S13 plus the fan box, on the 20 m lattice.

Writes perimeter.json (the staircase ring and the two outlet edges, RAS) and domain_wadi_<dx>m.geojson (the same
cells plus one row of boundary cells outside the outlet edges, Wadi2D), and terrain/bidah_0p5m.tif, then the RAS
terrain from the same clip.

usage: python s01_domain.py [--terrain]
"""

from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import rasterio
import rasterio.features
from rasterio.windows import Window
from scipy import ndimage
import shapely
from shapely import geometry

import case

sys.path.insert(0, str(case.BLOCK2_SCRIPTS))
from common import polygons  # noqa: E402

SYN = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)


def lattice_mask() -> tuple[np.ndarray, int, int]:
    """Cells of the 20 m lattice whose centre lies in S13 or the box; (mask, rows, columns)."""
    p = polygons()
    s13 = shapely.union_all([p[n].buffer(1.0) for n in case.SUBBASINS]).buffer(-1.0)
    box = geometry.box(case.BOX_WEST, case.BOX_SOUTH, case.BOX_EAST, case.BOX_NORTH)
    nx = round((case.BOX_EAST - case.X0) / case.COARSE)
    ny = round((case.Y0 - s13.bounds[1]) / case.COARSE) + 2
    t = rasterio.transform.from_origin(case.X0, case.Y0, case.COARSE, case.COARSE)
    m = rasterio.features.geometry_mask([s13, box], out_shape=(ny, nx), transform=t, invert=True)
    m = ndimage.binary_fill_holes(m)
    for _ in range(50):
        changed = False
        # two cells touching only at a corner would pinch the perimeter: fill one of the other two
        a, b = m[:-1, :-1], m[:-1, 1:]
        c, d = m[1:, :-1], m[1:, 1:]
        p1 = a & d & ~b & ~c
        p2 = b & c & ~a & ~d
        for j, i in zip(*np.nonzero(p1), strict=True):
            m[j, i + 1] = True
            changed = True
        for j, i in zip(*np.nonzero(p2), strict=True):
            m[j, i] = True
            changed = True
        labels, n = ndimage.label(m, structure=SYN)
        if n > 1:
            sizes = ndimage.sum(m, labels, range(1, n + 1))
            m = labels == 1 + int(np.argmax(sizes))
            changed = True
        if not changed:
            break
    return m, ny, nx


def ring_of(mask: np.ndarray, dx: float, x0: float, y0: float) -> np.ndarray:
    """The outline of a one-piece mask, clockwise from its first vertex, closed, corners only."""
    shapes = list(rasterio.features.shapes(mask.astype(np.uint8), mask=mask, connectivity=4))
    if len(shapes) != 1:
        raise ValueError(f"{len(shapes)} pieces")
    rings = shapes[0][0]["coordinates"]
    if len(rings) != 1:
        raise ValueError(f"{len(rings) - 1} holes")
    c = np.round(np.array(rings[0], np.float64)).astype(np.int64)  # (col, row) corners
    keep = [0]
    n = len(c) - 1
    for k in range(1, n):
        a, b, d = c[k - 1], c[k], c[k + 1]
        if (b[0] - a[0]) * (d[1] - b[1]) != (b[1] - a[1]) * (d[0] - b[0]):
            keep.append(k)
    c = np.vstack((c[keep], c[keep[0]]))
    xy = np.column_stack((x0 + c[:, 0] * dx, y0 - c[:, 1] * dx))
    area2 = np.sum(xy[:-1, 0] * xy[1:, 1] - xy[1:, 0] * xy[:-1, 1])
    return xy[::-1] if area2 > 0.0 else xy  # clockwise, as the Fan project


def pull_in(ring: np.ndarray, delta: float = case.PERIMETER_INSET) -> np.ndarray:
    """The ring moved in by ``delta``, mitred, so RAS's mesh generator meets no concave corner on a Voronoi vertex."""
    g = geometry.Polygon(ring).buffer(-delta, join_style="mitre", mitre_limit=10.0)
    if g.geom_type != "Polygon" or len(g.interiors):
        raise ValueError("the inset ring broke up")
    xy = np.array(g.exterior.coords)
    area2 = np.sum(xy[:-1, 0] * xy[1:, 1] - xy[1:, 0] * xy[:-1, 1])
    return xy[::-1] if area2 > 0.0 else xy


def wadi_mask(coarse: np.ndarray, dx: float) -> tuple[np.ndarray, float, float, np.ndarray]:
    """The same cells on the dx lattice with one more row and column outside the outlets; the strip's mask too."""
    k = round(case.COARSE / dx)
    fine = np.repeat(np.repeat(coarse, k, axis=0), k, axis=1)
    ny, nx = fine.shape
    out = np.zeros((ny + 1, nx + 1), bool)
    out[1:, :-1] = fine
    i_west = round((case.BOX_WEST - case.X0) / dx)
    j_south = 1 + round((case.Y0 - case.BOX_SOUTH) / dx)
    strip = np.zeros_like(out)
    j_north = 1 + round((case.Y0 - case.BOX_NORTH) / dx)
    strip[j_north:j_south, nx] = True  # east of the east outlet
    return out | strip, case.X0, case.Y0 + dx, strip


def clip_terrain(bounds: tuple[float, float, float, float]) -> None:
    """A plain window of the source DEM: same pixels, same corners."""
    case.DEM.parent.mkdir(exist_ok=True)
    with rasterio.open(case.DEM_SOURCE) as s:
        t = s.transform
        c0 = int(np.floor((bounds[0] - t.c) / t.a))
        c1 = int(np.ceil((bounds[2] - t.c) / t.a))
        r0 = int(np.floor((t.f - bounds[3]) / -t.e))
        r1 = int(np.ceil((t.f - bounds[1]) / -t.e))
        w = Window(c0, r0, c1 - c0, r1 - r0)
        prof = s.profile
        prof.update(width=w.width, height=w.height, transform=s.window_transform(w), compress="deflate", predictor=3,
                    tiled=True, blockxsize=512, blockysize=512, bigtiff="YES")  # fmt: skip
        with rasterio.open(case.DEM, "w", **prof) as d:
            for row in range(0, w.height, 2048):
                part = Window(c0, r0 + row, w.width, min(2048, w.height - row))
                d.write(s.read(1, window=part), 1, window=Window(0, row, w.width, part.height))
    print("clip", case.DEM, w)


def main() -> None:
    m, ny, nx = lattice_mask()
    area = m.sum() * case.COARSE**2 / 1e6
    ring = pull_in(ring_of(m, case.COARSE, case.X0, case.Y0))
    d = case.PERIMETER_INSET
    out = {
        "dx": case.COARSE, "x0": case.X0, "y0": case.Y0, "rows": ny, "cols": nx,
        "cells_20m": int(m.sum()), "area_km2": float(area), "ring": ring.tolist(),
        "east_outlet": [[case.BOX_EAST - d, case.BOX_SOUTH + d], [case.BOX_EAST - d, case.BOX_NORTH - d]],
    }  # fmt: skip
    (case.HERE / "perimeter.json").write_text(json.dumps(out), encoding="utf-8")
    np.save(case.HERE / "mask_20m.npy", m)
    print(f"cells {m.sum()} area {area:.3f} km2, ring {len(ring)} vertices")
    for dx in (20.0, 10.0):
        w, x0, y0, strip = wadi_mask(m, dx)
        r = ring_of(w, dx, x0, y0)
        gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "faydh"},
              "geometry": {"type": "Polygon", "coordinates": [r.tolist()]}}]}  # fmt: skip
        (case.HERE / f"domain_wadi_{dx:g}m.geojson").write_text(json.dumps(gj), encoding="utf-8")
        print(f"wadi {dx:g} m: cells {w.sum()}, strip {strip.sum()}, ring {len(r)}")
    if "--terrain" in sys.argv:
        margin = 60.0
        clip_terrain((case.X0 - margin, case.Y0 - ny * case.COARSE - margin, case.BOX_EAST + margin, case.Y0 + margin))
        folder = case.HERE / "ras_terrain"
        folder.mkdir(exist_ok=True)
        prj = case.W1.parent / "ras_head_to_head" / "ras_common" / "Projection UTM40.prj"
        subprocess.run(
            [case.RASPROCESS, "CreateTerrain", "units=Meter", "stitch=false", f"prj={prj}",
             f"out={folder / 'Terrain.hdf'}", str(case.DEM)],
            check=True,
        )  # fmt: skip


if __name__ == "__main__":
    main()
