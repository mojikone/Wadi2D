"""What the objects did to the ground: cut and fill, the modified terrain, a section and long-profile preview.

The tally walks the same tiles and the same edits as the table builder, one tile at a time, so the volumes are the
volumes of the ground the solver sees, and an object that runs out of the domain is counted only inside it.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio.transform import Affine

from wadi2d.config.schema import SHAPED_KINDS, Terrain, TerrainObject
from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import TILE
from wadi2d.terrain.alignment import Alignment
from wadi2d.terrain.earthworks import Sampler, Shape
from wadi2d.terrain.objects import TerrainEdits

MODIFIED_TIF = "terrain_modified.tif"
CHANGE_TIF = "terrain_change.tif"
VOLUMES_CSV = "volumes.csv"
STATIONS_CSV = "volumes_by_station.csv"
PREVIEW_JSON = "preview.json"
NODATA = -9999.0
BLOCK = 256
REACH_MARGIN = 1.1
"""The level range comes from a decimated read: a peak between its samples must not shorten the reach."""
EPS_CHANGE = 1e-9


@dataclass
class Tally:
    """Cut and fill of one object, per station bin."""

    obj: TerrainObject
    line: Alignment
    step: float
    cut: np.ndarray
    fill: np.ndarray

    @classmethod
    def of(cls, obj: TerrainObject, step: float) -> Tally:
        line = Alignment(obj.coordinates)
        bins = max(int(np.ceil(line.length / step)), 1)
        return cls(obj, line, step, np.zeros(bins), np.zeros(bins))

    def add(self, x: np.ndarray, y: np.ndarray, change: np.ndarray, pixel_area: float) -> None:
        bins = np.minimum((self.line.locate(x, y).s / self.step).astype(np.int64), self.cut.size - 1)
        np.add.at(self.fill, bins, np.maximum(change, 0.0) * pixel_area)
        np.add.at(self.cut, bins, np.maximum(-change, 0.0) * pixel_area)

    def title(self, index: int) -> str:
        return self.obj.name or f"{self.obj.kind} {index + 1}"


@dataclass
class TerrainReport:
    """The result of a survey."""

    volumes: list[dict] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    tiles: int = 0


def _rasters(folder: Path, grid: TileGrid, pixel: float, k: int, crs):
    profile = {
        "driver": "GTiff", "height": grid.shape[0] * k, "width": grid.shape[1] * k, "count": 1, "dtype": "float32",
        "nodata": NODATA, "crs": crs, "transform": Affine(pixel, 0.0, grid.x0, 0.0, -pixel, grid.y0),
        "compress": "deflate", "predictor": 2, "tiled": True, "blockxsize": BLOCK, "blockysize": BLOCK,
        "sparse_ok": True, "BIGTIFF": "IF_SAFER",
    }  # fmt: skip
    return rasterio.open(folder / MODIFIED_TIF, "w", **profile), rasterio.open(folder / CHANGE_TIF, "w", **profile)


def _near_tiles(grid: TileGrid, tallies: list[Tally], shapes: dict, levels: tuple[float, float]) -> set[int]:
    """Tiles an object can reach, from the level range of the whole raster."""
    size = TILE * grid.dx
    west = grid.x0 + grid.tiles[1:, 1] * size
    north = grid.y0 - grid.tiles[1:, 0] * size
    boxes = shapely.box(west, north - size, west + size, north)
    found: set[int] = set()
    for tally in tallies:
        shape = shapes.get(id(tally.obj))
        reach = shape.reach(*levels) * REACH_MARGIN if shape else float(tally.obj.width) + size
        near = np.flatnonzero(shapely.distance(tally.line.line, boxes) <= reach)
        found.update(int(t) + 1 for t in near)
    return found


def survey(
    cfg: Terrain,
    grid: TileGrid,
    bed,
    edits: TerrainEdits,
    folder: Path,
    crs,
    whole_map: bool = False,
    write_maps: bool = True,
) -> TerrainReport:
    """Tally every object and write the tables, and the rasters if asked.

    Tiles no object reaches are left empty in the rasters unless ``whole_map`` asks for a full terrain.
    """
    folder.mkdir(parents=True, exist_ok=True)
    k = round(grid.dx / bed.pixel)
    tallies = [Tally.of(obj, cfg.volume_step) for obj, _edit in edits.steps]
    near = _near_tiles(grid, tallies, edits.shapes, bed.levels()) if tallies else set()
    report = TerrainReport(tiles=len(near))
    rasters = _rasters(folder, grid, bed.pixel, k, crs) if write_maps else None
    block = TILE * k
    try:
        for t in range(1, grid.ntiles) if whole_map and write_maps else sorted(near):
            tj, ti = grid.tiles[t]
            row0, col0 = int(tj) * block, int(ti) * block
            old = bed.read(row0, col0, block, block)
            z = old.copy()
            if t in near:
                _tile(z, row0, col0, edits, tallies, grid, bed.pixel)
            if rasters is not None:
                window = rasterio.windows.Window(col0, row0, block, block)
                rasters[0].write(z.astype(np.float32), 1, window=window)
                rasters[1].write((z - old).astype(np.float32), 1, window=window)
    finally:
        if rasters is not None:
            for raster in rasters:
                raster.close()
    report.volumes = _write_tables(tallies, folder)
    report.files = {"volumes": str(folder / VOLUMES_CSV), "stations": str(folder / STATIONS_CSV)}
    if write_maps:
        report.files |= {"modified": str(folder / MODIFIED_TIF), "change": str(folder / CHANGE_TIF)}
    return report


def _tile(z, row0, col0, edits: TerrainEdits, tallies: list[Tally], grid: TileGrid, pixel: float) -> None:
    west = grid.x0 + col0 * pixel
    north = grid.y0 - row0 * pixel
    for (_obj, edit), tally in zip(edits.steps, tallies, strict=True):
        before = z.copy()
        edit(z, row0, col0)
        r, c = np.nonzero(np.abs(z - before) > EPS_CHANGE)
        if r.size:
            x, y = west + (c + 0.5) * pixel, north - (r + 0.5) * pixel
            tally.add(x, y, (z - before)[r, c], pixel * pixel)


def _write_tables(tallies: list[Tally], folder: Path) -> list[dict]:
    totals = []
    with (folder / STATIONS_CSV).open("w", newline="", encoding="utf-8") as stream:
        rows = csv.writer(stream)
        rows.writerow(("object", "kind", "station_from", "station_to", "cut_m3", "fill_m3"))
        for index, tally in enumerate(tallies):
            name = tally.title(index)
            for b in range(tally.cut.size):
                top = min((b + 1) * tally.step, tally.line.length)
                rows.writerow((name, tally.obj.kind, b * tally.step, top, f"{tally.cut[b]:.3f}", f"{tally.fill[b]:.3f}"))
            totals.append(
                {"object": name, "kind": tally.obj.kind, "cut_m3": float(tally.cut.sum()), "fill_m3": float(tally.fill.sum())}
            )
    with (folder / VOLUMES_CSV).open("w", newline="", encoding="utf-8") as stream:
        rows = csv.writer(stream)
        rows.writerow(("object", "kind", "cut_m3", "fill_m3"))
        for row in totals:
            rows.writerow((row["object"], row["kind"], f"{row['cut_m3']:.3f}", f"{row['fill_m3']:.3f}"))
    return totals


def _state(shape: Shape, s: np.ndarray, side: str, ground: Sampler, cfg: Terrain) -> list[str]:
    """What a bank is at each station: dyke, cut or open."""
    right = side == "right"
    sec, offset = shape.crest_offsets(s, right)
    g = ground(*shape.line.offset_at(s, offset))
    if not shape.fills:
        return ["cut" if value else "none" for value in g > sec.bed]
    state = np.where(g < sec.top - cfg.dyke_min_height, "dyke", "cut")
    for opening in shape.obj.openings:
        state = np.where(shape.opening_mask(opening, s, right), "open", state)
    return [str(v) for v in state]


def _cross_section(shape: Shape, station: float, ground: Sampler, half: float, points: int) -> dict:
    offsets = np.linspace(-half, half, points)
    s = np.full(offsets.shape, station)
    x, y = shape.line.offset_at(s, offsets)
    g = ground(x, y)
    return {
        "station": station,
        "offset": np.round(offsets, 3).tolist(),
        "ground": np.round(g, 3).tolist(),
        "new": np.round(shape.surface(x, y, g), 3).tolist(),
    }


def preview_data(objects: list[TerrainObject], ground: Sampler, dx: float, cfg: Terrain, shapes: dict) -> list[dict]:
    """Long profile and cross-sections of every shaped object, for the plugin to draw."""
    out = []
    for index, obj in enumerate(o for o in objects if o.kind in SHAPED_KINDS):
        shape = shapes[id(obj)]
        s = shape.line.samples(dx)
        x, y = shape.line.point_at(s)
        g = ground(x, y)
        new = shape.surface(x, y, g)
        left, right = shape.section(s, False), shape.section(s, True)
        band = float(shape.reach(float(g.min()), float(g.max())))
        stations = np.linspace(0.0, shape.line.length, cfg.preview_sections)
        out.append(
            {
                "name": obj.name or f"{obj.kind} {index + 1}",
                "kind": obj.kind,
                "length": shape.line.length,
                "station": np.round(s, 3).tolist(),
                "ground": np.round(g, 3).tolist(),
                "new": np.round(new, 3).tolist(),
                "bed": np.round(left.bed, 3).tolist(),
                "left_top": np.round(left.top, 3).tolist(),
                "right_top": np.round(right.top, 3).tolist(),
                "left_state": _state(shape, s, "left", ground, cfg),
                "right_state": _state(shape, s, "right", ground, cfg),
                "sections": [_cross_section(shape, float(v), ground, band, cfg.preview_points) for v in stations],
            }
        )
    return out


def write_preview(data: list[dict], folder: Path) -> Path:
    path = folder / PREVIEW_JSON
    path.write_text(json.dumps(data), encoding="utf-8")
    return path
