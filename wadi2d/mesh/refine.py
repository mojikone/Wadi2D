"""Which tiles refine: the rules of the mesher, as pure array arithmetic on the lattice of finest tiles.

Refine where the ground or the flow changes, not where it is steep. A uniform slope stays coarse: the sub-grid tables carry
its storage and conveyance. Defined wadis stay fine by drainage area, because W3 measured that refining by change of slope
alone lost 18 % of a wadi peak. Lines that must sit on faces of the finest lattice, and zones, are the user's.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely
from rasterio import features
from rasterio.transform import Affine

from wadi2d.config.schema import Mesh
from wadi2d.mesh.streams import Terrain, incision, slope_change
from wadi2d.solver.layout import TILE


@dataclass
class Lattice:
    """The lattice of finest tiles: origin at the padded grid's north-west corner."""

    x0: float
    y0: float
    dx: float
    ny: int
    nx: int

    @property
    def size(self) -> float:
        return self.dx * TILE

    def transform(self) -> Affine:
        return Affine(self.size, 0.0, self.x0, 0.0, -self.size, self.y0)


def squares(flags: np.ndarray, per_square: int) -> np.ndarray:
    """Count of True pixels per lattice square, for pixels aligned to the lattice."""
    ny, nx = flags.shape[0] // per_square, flags.shape[1] // per_square
    return (
        flags[: ny * per_square, : nx * per_square].reshape(ny, per_square, nx, per_square).sum(axis=(1, 3))
    )


def stream_levels(t: Terrain, inside: np.ndarray, cfg: Mesh, per_square: int, top: int) -> np.ndarray:
    """Wanted level per lattice square from defined wadis: finest on the big ones, one step coarser on the small."""
    wadi = (incision(t.z, t.pixel, cfg.incision_width) >= cfg.incision_depth) & inside
    big = squares((t.area >= cfg.stream_area_fine_km2 * 1e6) & wadi, per_square) >= cfg.stream_pixels
    small = squares((t.area >= cfg.stream_area_mid_km2 * 1e6) & wadi, per_square) >= cfg.stream_pixels
    level = np.full(big.shape, top, np.int32)
    level[small] = max(top - 1, 0)
    level[big] = 0
    return level


def break_levels(t: Terrain, inside: np.ndarray, cfg: Mesh, per_square: int, top: int) -> np.ndarray:
    """Wanted level per lattice square from banks and slope breaks, one step finer than coarse at most."""
    out = np.full((inside.shape[0] // per_square, inside.shape[1] // per_square), top, np.int32)
    if cfg.break_depth <= 0.0 or top == 0:
        return out
    change = slope_change(t.z, t.pixel, cfg.coarse_dx) >= cfg.break_depth
    share = squares(change & inside, per_square) / np.maximum(squares(inside, per_square), 1)
    out[share >= cfg.break_share] = top - 1
    return out


def line_levels(lines: list[list[tuple[float, float]]], lat: Lattice, reach: float, top: int) -> np.ndarray:
    """Level 0 on the squares a line touches, within ``reach`` of it: faces of a line must be on the finest lattice."""
    out = np.full((lat.ny, lat.nx), top, np.int32)
    shapes = [shapely.LineString(c).buffer(reach) for c in lines]
    if shapes:
        hit = features.rasterize(
            [(s, 1) for s in shapes],
            out_shape=out.shape,
            transform=lat.transform(),
            all_touched=True,
            dtype="uint8",
        ).astype(bool)
        out[hit] = 0
    return out


def zone_levels(cfg: Mesh, lat: Lattice, top: int) -> np.ndarray:
    """Wanted level from the user's zones; a later zone does not coarsen an earlier one."""
    out = np.full((lat.ny, lat.nx), top, np.int32)
    for zone in cfg.zones:
        level = int(np.clip(np.floor(np.log2(zone.dx / lat.dx) + 1e-9), 0, top))
        hit = features.rasterize(
            [(shapely.Polygon(zone.coordinates), 1)], out_shape=out.shape, transform=lat.transform(), all_touched=True,
            dtype="uint8",
        ).astype(bool)  # fmt: skip
        out[hit] = np.minimum(out[hit], level)
    return out


__all__ = ["Lattice", "break_levels", "line_levels", "squares", "stream_levels", "zone_levels"]
