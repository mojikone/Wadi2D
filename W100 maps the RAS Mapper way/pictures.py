"""Pictures of the maps of record in the plugin's own colours: depth over a hillshade, hazard classes, the cell grid.

    python pictures.py depth RASTER DEM XMIN YMIN XMAX YMAX OUT.png [--grid RUN] [--title TEXT] [--width PX]
    python pictures.py hazard RASTER DEM XMIN YMIN XMAX YMAX OUT.png [--grid RUN] [--title TEXT] [--width PX]

The colours are copied from ``plugin/wadi2d_qgis/style.py`` (that module imports QGIS): the pixel depth ramp of
``style_pixel_depth`` with the dock's default cutoff of 0.05 m, and the AIDR colours of ``style_pixel_hazard``. The
hillshade is the raw DEM, as the dock's own. ``--grid RUN`` draws the run's cells: the lattice and the aligned cells.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

DEPTH_ITEMS = ((0.0, "#ffffff", 0), (0.03, "#f7fbff", 255), (0.75, "#a2cae5", 255), (1.5, "#73b2d8", 255), (2.25, "#2979b9", 255), (3.0, "#08306b", 255))
"""style._ramp_items(WET_EDGE_M) with DEPTH_BLUES: depth m, colour, alpha."""
CUTOFF_M = 0.05
"""style.DEPTH_CUTOFF_M, the dock's default: below it a depth layer draws nothing."""
AIDR = ("#0000ff", "#0080ff", "#00ffff", "#00ff00", "#ffff00", "#ff0000")
"""style.AIDR_COLOURS, H1 to H6."""


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))


def read(path: Path, bounds, width: int, resampling=Resampling.nearest):
    """The raster over ``bounds`` at ``width`` pixels across, masked where nodata or out of the raster."""
    with rasterio.open(path) as src:
        window = from_bounds(*bounds, transform=src.transform)
        height = max(1, round(width * (bounds[3] - bounds[1]) / (bounds[2] - bounds[0])))
        a = src.read(1, window=window, out_shape=(height, width), boundless=True, masked=True, resampling=resampling)
    return a


def hillshade(dem: Path, bounds, width: int) -> np.ndarray:
    z = read(dem, bounds, width, Resampling.bilinear).astype(np.float64).filled(np.nan)
    pixel = (bounds[2] - bounds[0]) / width
    gy, gx = np.gradient(np.nan_to_num(z, nan=np.nanmean(z)), pixel)
    azimuth, altitude = np.radians(315.0), np.radians(45.0)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    shade = np.sin(altitude) * np.cos(slope) + np.cos(altitude) * np.sin(slope) * np.cos(azimuth - aspect)
    grey = np.clip(60 + 180 * shade, 0, 255)
    return np.repeat(grey[..., None], 3, axis=2)


def depth_rgba(depth: np.ma.MaskedArray) -> np.ndarray:
    d = depth.filled(0.0).astype(np.float64)
    values = np.array([v for v, _c, _a in DEPTH_ITEMS])
    colours = np.array([[*_rgb(c), a] for _v, c, a in DEPTH_ITEMS], np.float64)
    out = np.stack([np.interp(np.clip(d, 0, values[-1]), values, colours[:, i]) for i in range(4)], axis=-1)
    out[(d < CUTOFF_M) | np.ma.getmaskarray(depth)] = 0.0
    return out


def hazard_rgba(classes: np.ma.MaskedArray) -> np.ndarray:
    c = classes.filled(0).astype(np.int64)
    out = np.zeros((*c.shape, 4))
    for index, colour in enumerate(AIDR, start=1):
        out[c == index] = [*_rgb(colour), 255]
    return out


def cell_lines(run: Path, bounds, width: int, height: int):
    """Line segments (pixel coordinates) of the run's cells in ``bounds``: lattice cell edges, aligned cell rings."""
    import json

    import shapely
    from shapely import wkb

    cfg = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
    sx = width / (bounds[2] - bounds[0])
    sy = height / (bounds[3] - bounds[1])

    def to_px(x, y):
        return (x - bounds[0]) * sx, (bounds[3] - y) * sy

    segments = []
    import h5py

    with h5py.File(run / "results.h5", "r") as f:
        x0, y0, dx = (float(f.attrs[n]) for n in ("x0", "y0", "dx"))
        mask = f["mask"][:]
    c0, c1 = int((bounds[0] - x0) // dx), int((bounds[2] - x0) // dx) + 1
    r0, r1 = int((y0 - bounds[3]) // dx), int((y0 - bounds[1]) // dx) + 1
    for r in range(max(r0, 0), min(r1, mask.shape[0])):
        for c in range(max(c0, 0), min(c1, mask.shape[1])):
            if not mask[r, c]:
                continue
            xa, ya = x0 + c * dx, y0 - r * dx
            corners = [to_px(xa, ya), to_px(xa + dx, ya), to_px(xa + dx, ya - dx), to_px(xa, ya - dx)]
            segments.append(corners + corners[:1])
    strip = run / "maps" / "strip_mesh.gpkg"
    if cfg.get("strips", {}).get("enabled") and strip.is_file():
        box = shapely.box(*bounds)
        with sqlite3.connect(strip) as db:
            rtree = [r[0] for r in db.execute("select name from sqlite_master where name like 'rtree_strip_cells_geom'")]
            if rtree:
                rows = db.execute(
                    "select c.geom from strip_cells c join rtree_strip_cells_geom r on c.fid = r.id "
                    "where r.maxx >= ? and r.minx <= ? and r.maxy >= ? and r.miny <= ?",
                    (bounds[0], bounds[2], bounds[1], bounds[3]),
                ).fetchall()
            else:
                rows = db.execute("select geom from strip_cells").fetchall()
        for (blob,) in rows:
            geom = _gpkg_geometry(blob, wkb)
            if geom is None or not geom.intersects(box):
                continue
            for ring in getattr(geom, "geoms", [geom]):
                xs, ys = ring.exterior.coords.xy
                segments.append([to_px(x, y) for x, y in zip(xs, ys, strict=True)])
    return segments


def _gpkg_geometry(blob: bytes, wkb):
    """A GeoPackage geometry blob as shapely: the GP header, then WKB."""
    if blob is None or blob[:2] != b"GP":
        return None
    flags = blob[3]
    envelope = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get((flags >> 1) & 0x07, 0)
    return wkb.loads(bytes(blob[8 + envelope :]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("depth", "hazard"))
    parser.add_argument("raster", type=Path)
    parser.add_argument("dem", type=Path)
    parser.add_argument("bounds", nargs=4, type=float)
    parser.add_argument("out", type=Path)
    parser.add_argument("--grid", type=Path, default=None)
    parser.add_argument("--title", default="")
    parser.add_argument("--width", type=int, default=1400)
    args = parser.parse_args()
    bounds = tuple(args.bounds)
    shade = hillshade(args.dem, bounds, args.width)
    values = read(args.raster, bounds, args.width)
    over = depth_rgba(values) if args.kind == "depth" else hazard_rgba(values)
    alpha = over[..., 3:4] / 255.0
    picture = shade * (1 - alpha) + over[..., :3] * alpha
    image = Image.fromarray(np.clip(picture, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image, "RGBA")
    if args.grid is not None:
        for line in cell_lines(args.grid, bounds, image.width, image.height):
            draw.line(line, fill=(60, 60, 60, 110), width=1)
    if args.title:
        font = ImageFont.load_default(size=18)
        draw.rectangle((0, 0, image.width, 28), fill=(255, 255, 255, 210))
        draw.text((8, 4), args.title, fill=(0, 0, 0, 255), font=font)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
