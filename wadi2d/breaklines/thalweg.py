"""Thalwegs: the D8 stream network walked downstream, one polyline between heads and junctions.

A stream is where the drainage area passes the mesher's smaller wadi threshold. The thalweg itself is never a
breakline: it is the row of cells the banks stand either side of, and it goes to the file for reference only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.breaklines.pixels import simplify, smooth
from wadi2d.breaklines.window import POINTER_STEPS, Window
from wadi2d.config.schema import Mesh
from wadi2d.mesh.streams import incision


@dataclass
class Thalweg:
    pixels: np.ndarray
    """(n, 2) rows and columns walked downstream."""
    xy: np.ndarray
    """(m, 2) the smoothed, simplified line."""
    area_km2: float
    """Drainage area at the downstream end."""
    incised_m: float
    """Mean incision along it."""


def downstream(pointer: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Row and column of the pixel each pixel drains to; -1 where it drains nowhere."""
    ny, nx = pointer.shape
    rows, cols = np.indices(pointer.shape)
    dj = np.zeros(pointer.shape, np.int64)
    di = np.zeros(pointer.shape, np.int64)
    has = np.zeros(pointer.shape, bool)
    for code, (sj, si) in POINTER_STEPS.items():
        hit = pointer == code
        dj[hit], di[hit] = sj, si
        has |= hit
    tj, ti = rows + dj, cols + di
    ok = has & (tj >= 0) & (tj < ny) & (ti >= 0) & (ti < nx)
    return np.where(ok, tj, -1), np.where(ok, ti, -1)


def trace(mask: np.ndarray, pointer: np.ndarray) -> list[np.ndarray]:
    """Polylines of (row, col) along the stream mask: from each head or junction down to the next junction or end."""
    tj, ti = downstream(pointer)
    into = np.zeros(mask.shape, np.int64)
    j, i = np.nonzero(mask)
    goes = (tj[j, i] >= 0) & mask[np.maximum(tj[j, i], 0), np.maximum(ti[j, i], 0)]
    np.add.at(into, (tj[j, i][goes], ti[j, i][goes]), 1)
    starts = [(int(a), int(b)) for a, b in zip(j, i, strict=True) if into[a, b] != 1]
    lines = []
    for start in sorted(starts):
        path = [start]
        while True:
            a, b = path[-1]
            nj, ni = int(tj[a, b]), int(ti[a, b])
            if nj < 0 or not mask[nj, ni]:
                break
            path.append((nj, ni))
            if into[nj, ni] != 1:
                break
        if len(path) >= 2:
            lines.append(np.array(path, np.int64))
    return lines


def thalwegs(
    win: Window, area: np.ndarray, pointer: np.ndarray, mesh: Mesh, tolerance: float, vertices: int
) -> list[Thalweg]:
    """The streams of the window, as the mesher counts them, walked and smoothed."""
    mask = (area >= mesh.stream_area_mid_km2 * 1e6) & win.inside
    cut = incision(win.z, win.pixel, mesh.incision_width)
    out = []
    for pixels in trace(mask, pointer):
        xy = simplify(smooth(win.xy(pixels[:, 0], pixels[:, 1]), vertices), tolerance)
        last = pixels[-1]
        out.append(
            Thalweg(
                pixels,
                xy,
                float(area[last[0], last[1]]) * 1e-6,
                float(np.nanmean(cut[pixels[:, 0], pixels[:, 1]])),
            )
        )
    return out


__all__ = ["Thalweg", "downstream", "thalwegs", "trace"]
