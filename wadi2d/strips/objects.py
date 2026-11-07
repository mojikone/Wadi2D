# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Terrain objects on a strip's faces (W45, stage 6): the same objects the squares carry, on aligned faces.

The lattice rasterises a crest line, a spillway, a wall or the standing stretches of a shaped object into a staircase
of faces (:mod:`wadi2d.terrain.objects`); the pixel edits of burn lines and shaped objects reach the strip through
the same ``edit`` hook as the squares. Here the faces are the strip's own: a face carries the object when its two
cells lie on different sides of the object's line, the rule the result lines use, so a crest drawn along a bank row
sits on that row's faces exactly, with no staircase and no length factor. The face's invert is lifted to the crest's
elevation at the nearest point of the line (the higher of two crests wins; a spillway sets its own), the face takes
the object's coefficient (positive the plain critical limit, negative the energy head of a shaped crest), and a wall
closes the face.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely

from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.config.schema import SHAPED_KINDS, Terrain
from wadi2d.terrain.crest import elevations_along, line_lengths
from wadi2d.terrain.earthworks import crest_coefficient


@dataclass
class CrestPolyline:
    """A line a strip face can carry: its vertices, the elevation at each, the coefficient, or a wall."""

    coordinates: np.ndarray
    z: np.ndarray
    coefficient: float
    wall: bool = False
    keep_max: bool = True
    """Whether a higher crest already on the face stands; a spillway sets its own level instead."""


def crest_polylines(objects, dx: float, cfg: Terrain, ground, shapes: dict) -> list[CrestPolyline]:
    """The lines of the job's objects in the lattice's order: crests and shaped stretches, spillways, walls."""
    first: list[CrestPolyline] = []
    second: list[CrestPolyline] = []
    third: list[CrestPolyline] = []
    for obj in objects:
        coords = np.asarray(obj.coordinates, np.float64)
        if obj.kind == "crest_line":
            z = elevations_along(obj.coordinates, obj.z, obj.z_constant, line_lengths(obj.coordinates))
            first.append(CrestPolyline(coords, np.asarray(z, np.float64), CRITICAL_WEIR_COEFF))
        elif obj.kind in SHAPED_KINDS:
            shape = shapes.get(id(obj))
            if shape is None:
                continue
            for run in shape.crest_runs(dx, cfg, ground):
                c = crest_coefficient(run.width, dx, cfg)
                first.append(CrestPolyline(np.asarray(run.coordinates, np.float64), np.asarray(run.z, np.float64), c))
        elif obj.kind == "spillway":
            z = elevations_along(obj.coordinates, obj.z, obj.z_constant, line_lengths(obj.coordinates))
            second.append(CrestPolyline(coords, np.asarray(z, np.float64), obj.coefficient, keep_max=False))
        elif obj.kind == "wall":
            third.append(CrestPolyline(coords, np.zeros(coords.shape[0]), 0.0, wall=True))
    return first + second + third


def separating_faces(
    line: shapely.LineString, lx, ly, rx, ry, xf, yf, reach, defined=None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The faces whose two cells (centres ``l`` and ``r``) lie on different sides of a polyline, the side of the left
    cell (+1 left of the line), and the distance along the line of each face's nearest point.

    A cell is left or right by its centroid against the nearest stretch of the line. Faces past the line's ends,
    which that stretch would still take sides on, stay out: a face there is excluded when its midpoint projects onto
    an end and lies further than ``reach`` from it. ``defined`` marks faces whose two cells both exist.
    """
    parts = np.asarray(line.coords)[:, :2]
    seg = np.diff(parts, axis=0)
    cum = np.concatenate(([0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))))

    def side(x, y):
        pts = shapely.points(np.column_stack((x, y)))
        s = shapely.line_locate_point(line, pts)
        k = np.clip(np.searchsorted(cum, s, side="right") - 1, 0, seg.shape[0] - 1)
        px, py = np.asarray(shapely.get_coordinates(shapely.line_interpolate_point(line, s))).T
        cross = seg[k, 0] * (y - py) - seg[k, 1] * (x - px)
        return np.where(cross >= 0.0, 1.0, -1.0)

    sl, sr = side(np.asarray(lx), np.asarray(ly)), side(np.asarray(rx), np.asarray(ry))
    across = sl != sr
    if defined is not None:
        across &= np.asarray(defined, bool)
    faces = np.nonzero(across)[0]
    if faces.size == 0:
        return faces, np.zeros(0), np.zeros(0)
    mids = shapely.points(np.column_stack((np.asarray(xf)[faces], np.asarray(yf)[faces])))
    s = np.asarray(shapely.line_locate_point(line, mids))
    at_end = (s <= 1e-6) | (s >= line.length - 1e-6)
    beyond = at_end & (np.asarray(shapely.distance(line, mids)) > np.asarray(reach)[faces])
    keep = ~beyond
    return faces[keep], sl[faces[keep]], s[keep]


def faces_from_objects(geo, ghosts, lines: list[CrestPolyline]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per geometry face: the crest elevation (NaN where no object), the coefficient, and whether a wall closes it."""
    nf = geo.nfaces
    crest = np.full(nf, np.nan)
    cw = np.zeros(nf)
    wall = np.zeros(nf, bool)
    if not lines:
        return crest, cw, wall
    area, cx, cy = geo.areas_centroids()
    _length, _nfx, _nfy, xf, yf = geo.faces(cx, cy)
    left, right = geo.face_cell[:, 0], geo.face_cell[:, 1]
    slot = np.asarray(ghosts.face_slot, np.int64) if ghosts is not None else np.full(nf, -1, np.int64)
    has_right = right >= 0
    has_ghost = slot >= 0
    rx = np.where(has_right, cx[np.maximum(right, 0)], 0.0)
    ry = np.where(has_right, cy[np.maximum(right, 0)], 0.0)
    ra = np.where(has_right, area[np.maximum(right, 0)], 0.0)
    if ghosts is not None and has_ghost.any():
        rx[has_ghost] = np.asarray(ghosts.cx)[slot[has_ghost]]
        ry[has_ghost] = np.asarray(ghosts.cy)[slot[has_ghost]]
        ra[has_ghost] = np.asarray(ghosts.area)[slot[has_ghost]]
    defined = has_right | has_ghost
    reach = 0.5 * np.sqrt(np.maximum(area[left], ra))
    for line in lines:
        shape = shapely.LineString(line.coordinates)
        faces, _sides, s = separating_faces(shape, cx[left], cy[left], rx, ry, xf, yf, reach, defined)
        if faces.size == 0:
            continue
        if line.wall:
            wall[faces] = True
            continue
        z = np.interp(s, line_lengths(line.coordinates), line.z)
        old = crest[faces]
        # ``~`` on a Python bool is an integer, never False: it set every face to the line's own level (found 2026-11-07)
        crest[faces] = np.where(np.isnan(old) | (not line.keep_max), z, np.maximum(old, z))
        cw[faces] = line.coefficient
    return crest, cw, wall


__all__ = ["CrestPolyline", "crest_polylines", "faces_from_objects", "separating_faces"]
