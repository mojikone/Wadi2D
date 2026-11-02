"""Bank lines: sections across each thalweg, a bank where the ground rises out of the channel, one line per side.

The rules they follow, his of 2026-11-01: a row of cells runs along the thalweg with a bank line either side,
never a line on the thalweg; one bank only where one bank exists; no bank where the stream is not incised, so a
wadi crossing an open plain gets none and the flow finds its own way. The bank stands where the ground is the
mesher's incision depth above the bed, at least one cell from the thalweg, and no further than the half of the
incision window; past that, that side has no bank.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.breaklines.pixels import length_of, simplify, smooth
from wadi2d.breaklines.settings import LEFT, RIGHT, Settings
from wadi2d.breaklines.thalweg import Thalweg
from wadi2d.breaklines.window import Window
from wadi2d.config.schema import Mesh
from wadi2d.mesh.streams import incision


@dataclass
class Bank:
    xy: np.ndarray
    """(n, 2) plan vertices."""
    side: str
    incised_m: float
    """Mean incision of the sections that placed it."""
    area_km2: float


def sections(xy: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Centres every ``step`` along a polyline and the unit normal to its left, looking downstream."""
    seg = np.diff(xy, axis=0)
    seg_len = np.hypot(*seg.T)
    along = np.concatenate(([0.0], np.cumsum(seg_len)))
    if along[-1] <= 0.0:
        return np.zeros((0, 2)), np.zeros((0, 2))
    s = np.arange(0.0, along[-1] + 1e-9, step)
    k = np.clip(np.searchsorted(along, s, side="right") - 1, 0, len(seg) - 1)
    frac = np.where(seg_len[k] > 0.0, (s - along[k]) / np.maximum(seg_len[k], 1e-12), 0.0)
    centres = xy[k] + seg[k] * frac[:, None]
    direction = seg[k] / np.maximum(seg_len[k], 1e-12)[:, None]
    left = np.column_stack((-direction[:, 1], direction[:, 0]))
    return centres, left


def _bed(win: Window, centres: np.ndarray, normals: np.ndarray) -> np.ndarray:
    """Lowest ground within a pixel of each centre across the line: the smoothed thalweg sits a little off the pit."""
    offsets = np.array([-1.0, -0.5, 0.0, 0.5, 1.0]) * win.pixel
    z = np.stack([win.sample(win.z, centres + normals * d) for d in offsets])
    return np.nanmin(z, axis=0)


def bank_points(
    win: Window,
    centres: np.ndarray,
    normals: np.ndarray,
    bed: np.ndarray,
    sign: float,
    rise: float,
    reach: float,
    offset: float,
) -> np.ndarray:
    """One bank point per section, NaN where that side has no bank within ``reach`` of the thalweg."""
    distances = np.arange(win.pixel, reach + 1e-9, win.pixel)
    z = np.stack([win.sample(win.z, centres + sign * normals * d) for d in distances])
    risen = (z - bed[None, :]) >= rise
    off = np.isnan(z)
    first = np.argmax(risen, axis=0)
    found = risen.any(axis=0)
    seen_off = np.cumsum(off, axis=0)[first, np.arange(len(bed))] > 0
    ok = found & ~seen_off
    d = np.where(ok, np.maximum(distances[first], offset), np.nan)
    return centres + sign * normals * d[:, None]


def split_runs(points: np.ndarray, jump: float) -> list[np.ndarray]:
    """Indices of consecutive finite points, split where one is missing or the bank jumps by over ``jump``."""
    out: list[list[int]] = []
    current: list[int] = []
    for n, p in enumerate(points):
        if not np.all(np.isfinite(p)) or (current and np.hypot(*(p - points[current[-1]])) > jump):
            if current:
                out.append(current)
            current = []
        if np.all(np.isfinite(p)):
            current.append(n)
    if current:
        out.append(current)
    return [np.array(run) for run in out if len(run) >= 2]


def banks_of(win: Window, cut: np.ndarray, thalweg: Thalweg, mesh: Mesh, settings: Settings) -> list[Bank]:
    centres, normals = sections(thalweg.xy, settings.section_step_m)
    if len(centres) == 0:
        return []
    incised = win.sample(cut, centres)
    keep = incised >= mesh.incision_depth
    bed = _bed(win, centres, normals)
    reach = 0.5 * mesh.incision_width
    offset = settings.bank_offset_cells * win.dx
    jump = settings.bank_jump_steps * settings.section_step_m
    out = []
    for side, sign in ((LEFT, 1.0), (RIGHT, -1.0)):
        points = bank_points(win, centres, normals, bed, sign, mesh.incision_depth, reach, offset)
        points[~keep] = np.nan
        for run in split_runs(points, jump):
            xy = simplify(smooth(points[run], settings.smooth_vertices), settings.simplify_pixels * win.pixel)
            if length_of(xy) < settings.min_length_m:
                continue
            out.append(Bank(xy, side, float(np.nanmean(incised[run])), thalweg.area_km2))
    return out


def all_banks(win: Window, thalwegs: list[Thalweg], mesh: Mesh, settings: Settings) -> list[Bank]:
    cut = incision(win.z, win.pixel, mesh.incision_width)
    return [bank for t in thalwegs for bank in banks_of(win, cut, t, mesh, settings)]
