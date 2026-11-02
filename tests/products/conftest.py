"""A straight channel of known surface, on real tables: the freeboard check of the sloped water surface."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from wadi2d.config.schema import Pixels, Tables
from wadi2d.grid.tiles import TileGrid
from wadi2d.products.ground import CellPixels, face_sills
from wadi2d.products.pixels import PixelMaxima
from wadi2d.tables import ArrayBed, build_tables

CELL, SCALE, PIXEL = 30.0, 6, 5.0
NX, NY = 40, 9
WIDTH = 45.0
EDGE = 3
"""Cells at each end left out of the marks: the surface has nothing to lean on there."""


@dataclass
class Channel:
    water: np.ndarray
    ground: np.ndarray
    channel: np.ndarray
    level: np.ndarray
    fill_level: np.ndarray
    mean_depth: np.ndarray
    tables: object
    cells: CellPixels
    keep: np.ndarray


def channel_case(slope: float, freeboard: float, depth: float = 2.0) -> Channel:
    """Banks stand ``freeboard`` above the true surface; ``level`` is the mean surface over the wet pixels."""
    grid = TileGrid.from_mask(np.ones((NY, NX), bool), 0.0, NY * CELL, CELL)
    ny, nx = (a * SCALE for a in grid.shape)
    x = (np.arange(nx) + 0.5) * PIXEL + grid.x0
    y = grid.y0 - (np.arange(ny) + 0.5) * PIXEL
    gx, gy = np.meshgrid(x, y)
    centre = NY * CELL / 2 + 7.5  # so the walls fall inside cells
    channel = np.abs(gy - centre) <= WIDTH / 2
    water = 100.0 - slope * gx
    ground = np.where(channel, water - depth, water + freeboard)
    tables = build_tables(grid, ArrayBed(ground, PIXEL), Tables(), 0.04)
    shape = grid.shape

    def cellwise(a):
        return a.reshape(shape[0], SCALE, shape[1], SCALE).transpose(0, 2, 1, 3).reshape(*shape, SCALE**2)

    wet_px = cellwise(channel)
    water_px, ground_px = cellwise(water), cellwise(ground)
    held = wet_px.sum(axis=2)
    mean_depth = (np.maximum(water_px - ground_px, 0.0) * wet_px).mean(axis=2)
    level = np.full(shape, np.nan)
    has = held > 0
    level[has] = (water_px * wet_px).sum(axis=2)[has] / held[has]
    fill_level = np.full(shape, np.nan)
    ordered = np.sort(ground_px, axis=2)
    filled = np.cumsum(ordered, axis=2)
    count = np.arange(1, SCALE**2 + 1)
    needed = count * ordered - filled
    water_held = mean_depth[..., None] * SCALE**2
    pixels = np.maximum((needed <= water_held).sum(axis=2), 1)
    rows, cols = np.nonzero(has)
    picked = filled[rows, cols, pixels[rows, cols] - 1]
    fill_level[rows, cols] = (water_held[rows, cols, 0] + picked) / pixels[rows, cols]
    keep = has & grid.mask
    datum = float(tables.zmin[keep].min())
    cells = CellPixels(*np.nonzero(keep), SCALE, PIXEL, datum, (ground_px[keep] - datum).astype(np.float32))
    return Channel(water, ground, channel, level, fill_level, mean_depth, tables, cells, keep)


def surface_of(case: Channel, level: np.ndarray, flat: bool = False, xp=np) -> np.ndarray:
    """(cells, k * k) surface over the true datum, read back from the pixel depth."""
    tables, cells = case.tables, case.cells
    zmin = (tables.zmin - cells.datum).astype(np.float32)
    sill_x, sill_y = face_sills(tables, cells.datum)
    maxima = PixelMaxima(xp, cells, zmin, sill_x, sill_y, case.keep, Pixels(), flat=flat)
    depth = np.nan_to_num(level - tables.zmin, nan=0.0).astype(np.float32) * case.keep
    maxima.add(depth, case.mean_depth.astype(np.float32), np.zeros(depth.shape, np.float32))
    return maxima.result()[0]


def marks(case: Channel, depth: np.ndarray) -> dict[str, float]:
    """Share of bank pixels falsely wet, %, and the largest surface error in the channel, m."""
    k2 = SCALE**2
    pixels = case.ground.reshape(case.tables.grid.shape[0], SCALE, case.tables.grid.shape[1], SCALE)
    pixels = pixels.transpose(0, 2, 1, 3).reshape(*case.tables.grid.shape, k2)[case.keep]
    water = case.water.reshape(case.tables.grid.shape[0], SCALE, case.tables.grid.shape[1], SCALE)
    water = water.transpose(0, 2, 1, 3).reshape(*case.tables.grid.shape, k2)[case.keep]
    channel = case.channel.reshape(case.tables.grid.shape[0], SCALE, case.tables.grid.shape[1], SCALE)
    channel = channel.transpose(0, 2, 1, 3).reshape(*case.tables.grid.shape, k2)[case.keep]
    pad = 1  # the grid's own margin
    inner = (case.cells.cols >= pad + EDGE) & (case.cells.cols < pad + NX - EDGE)
    bank = ~channel[inner]
    error = np.abs(pixels + depth - water)[inner][channel[inner]]
    wet = depth[inner] >= Pixels().depth_floor
    return {"false_bank_pct": float(wet[bank].mean() * 100.0), "surface_error_m": float(error.max())}


@pytest.fixture
def channel():
    return channel_case
