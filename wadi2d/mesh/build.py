"""From a job to a QuadGrid: read the ground, ask the refinement rules, balance, and report what came out."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import rasterio
import shapely

from wadi2d.config.schema import SHAPED_KINDS, RunConfig
from wadi2d.grid.quad import QuadGrid, balance, pad_to_lattice
from wadi2d.io.geotiff import write_map
from wadi2d.mesh.refine import Lattice, break_levels, line_levels, squares, stream_levels, zone_levels
from wadi2d.mesh.streams import Terrain, drainage_area, read_coarse
from wadi2d.solver.layout import TILE
from wadi2d.terrain.earthworks import Shape

LINE_SPARE_CELLS = 1.0
"""A line refines the squares within this of it, past the join reach of ``apply_objects``, so that a face beside a tile
edge, or one a joined end walks to, is still on the finest lattice."""


def levels_above(cfg: RunConfig) -> int:
    """Tile size levels between the finest and the coarsest cell."""
    ratio = cfg.mesh.coarse_dx / cfg.grid.dx
    top = round(np.log2(ratio))
    if ratio < 1.0 or abs(2.0**top - ratio) > 1e-6:
        raise ValueError(
            f"mesh.coarse_dx {cfg.mesh.coarse_dx} m must be grid.dx {cfg.grid.dx} m times a power of two"
        )
    return int(top)


def must_be_fine(cfg: RunConfig, ground=None) -> list[list[tuple[float, float]]]:
    """Every line whose faces are read or edited: barriers, the crests of shaped objects, boundaries, design lines."""
    lines = [o.coordinates for o in cfg.terrain.objects if o.kind in ("crest_line", "wall", "spillway")]
    for obj in cfg.terrain.objects:
        if obj.kind in SHAPED_KINDS:
            runs = Shape.of(obj).crest_runs(cfg.grid.dx, cfg.terrain, ground)
            lines += [[tuple(point) for point in run.coordinates] for run in runs]
    lines += [b.coordinates for b in cfg.boundaries]
    lines += [h.coordinates for h in cfg.hydrology.handbacks]
    lines += [ln.coordinates for ln in cfg.outputs.lines]
    return lines


def worth_refining(cfg: RunConfig) -> list[list[tuple[float, float]]]:
    """Lines with no faces of their own, whose narrow ground a coarse cell would blur: channels and burns."""
    return [o.coordinates for o in cfg.terrain.objects if o.kind in (*SHAPED_KINDS, "burn_line")]


@dataclass
class MeshReport:
    """What a preview shows."""

    cells: int
    cells_uniform: int
    ratio: float
    tiles_by_size: dict[str, int]
    interfaces: int


def lattice_levels(cfg: RunConfig, mask: np.ndarray, x0: float, y0: float, crs, ground=None) -> np.ndarray:
    """The wanted level of every lattice square, before balancing."""
    m = cfg.mesh
    top = levels_above(cfg)
    dx = cfg.grid.dx
    lat = Lattice(x0, y0, dx, mask.shape[0] // TILE, mask.shape[1] // TILE)
    per_square = round(TILE * dx / m.analysis_pixel)
    factor = round(dx / m.analysis_pixel)
    if per_square < 1 or abs(per_square * m.analysis_pixel - TILE * dx) > 1e-6 * dx:
        raise ValueError(f"mesh.analysis_pixel {m.analysis_pixel} m must divide a tile of {TILE * dx} m")
    z = read_coarse(cfg.terrain.dem, x0, y0, mask.shape[0], mask.shape[1], dx, factor)
    area = drainage_area(z, m.analysis_pixel, x0, y0, crs)
    surface = Terrain(z, area, m.analysis_pixel)
    inside = np.repeat(np.repeat(mask, factor, axis=0), factor, axis=1) if factor > 1 else mask
    level = np.minimum(
        stream_levels(surface, inside, m, per_square, top), break_levels(surface, inside, m, per_square, top)
    )
    level = np.minimum(level, zone_levels(m, lat, top))
    if m.refine_lines:
        reach = (cfg.terrain.join_cells + LINE_SPARE_CELLS) * dx
        lines = must_be_fine(cfg, ground) + worth_refining(cfg)
        level = np.minimum(level, line_levels(lines, lat, reach, top))
    return level


def build_grid(cfg: RunConfig, mask: np.ndarray, x0: float, y0: float, crs, ground=None) -> QuadGrid:
    """A QuadGrid over ``mask``, whose origin (x0, y0) is its unpadded north-west corner.

    ``ground`` tells a shaped object where it stands above the ground, as in ``apply_objects``.
    """
    top = levels_above(cfg)
    padded, rows, cols = pad_to_lattice(mask, top)
    px, py = x0 - cols * cfg.grid.dx, y0 + rows * cfg.grid.dx
    level = lattice_levels(cfg, padded, px, py, crs, ground)
    return QuadGrid.from_levels(padded, px, py, cfg.grid.dx, level)


def lines_on_coarse_tiles(cfg: RunConfig, grid: QuadGrid, ground=None) -> int:
    """How many lines that sit on faces reach a coarse tile; their faces are not on the lattice the engine reads."""
    found = 0
    ny, nx = grid.shape
    for coordinates in must_be_fine(cfg, ground):
        line = shapely.LineString(coordinates)
        points = shapely.line_interpolate_point(line, np.arange(0.0, line.length, 0.5 * grid.dx))
        j = np.floor((grid.y0 - shapely.get_y(points)) / grid.dx).astype(np.int64)
        i = np.floor((shapely.get_x(points) - grid.x0) / grid.dx).astype(np.int64)
        keep = (j >= 0) & (j < ny) & (i >= 0) & (i < nx)
        tiles = grid.tile_of[j[keep] // TILE, i[keep] // TILE]
        found += int((grid.level[tiles] > 0).any())
    return found


def report(grid: QuadGrid, cells_uniform: int, dx: float) -> MeshReport:
    counts = np.bincount(grid.level[1:], minlength=int(grid.level.max()) + 1)
    return MeshReport(
        grid.cell_count, cells_uniform, round(cells_uniform / max(grid.cell_count, 1), 3),
        {f"{dx * (1 << s):g} m": int(n) for s, n in enumerate(counts)}, int(grid.interfaces.shape[0]),
    )  # fmt: skip


def write_preview(grid: QuadGrid, crs, folder: str | Path, summary: MeshReport) -> dict[str, str]:
    """The cell size as a raster and the numbers as JSON; what the plugin shows before a run."""
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    size = np.broadcast_to(grid.tile_dx[:, None, None], (grid.ntiles, TILE, TILE)).astype(np.float32)
    raster = grid.from_tiles(size)
    tif = write_map(out / "mesh_cell_size.tif", raster, grid, crs, None, {"content": "cell size, m"})
    js = out / "mesh.json"
    js.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    return {"raster": str(tif), "summary": str(js)}


def tile_share(grid: QuadGrid) -> np.ndarray:
    """Area of the domain per tile size, m2; for reports."""
    return np.bincount(grid.level[1:], weights=grid.cells[1:].sum(axis=(1, 2)) * grid.tile_dx[1:] ** 2)


def crs_of(dem: str | Path):
    with rasterio.open(dem) as src:
        return src.crs


__all__ = ["MeshReport", "balance", "build_grid", "lattice_levels", "report", "squares", "write_preview"]
