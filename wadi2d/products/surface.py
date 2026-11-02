"""The water surface inside a cell, from the levels of the cells around it.

A cell holds one level, so on a slope a flat surface reads high at the low end of each cell. Here a surface slopes
through its cell corners, and a corner takes the mean of the cells that are one body of water there. Whether two
cells are one body of water is decided at their shared face, from the ground of that face (the sub-grid face invert,
crest lines and walls included) and not from a fixed jump in level, so it follows connected flow at any slope:

- submerged: both levels stand above the face;
- stepping: the higher level stands above the face and the two depths are alike, which is one flow going down a
  slope steeper than the cells can follow. A hill sheet or a shallow steep channel is this; a thin film on a bank
  beside a deep channel is not.

Anything else keeps its own level, so a surface is never carried over a bank. ``xp`` is NumPy or CuPy, and ``near`` a
:class:`Neighbours` built on either: one source for both backends, in float32.
"""

from __future__ import annotations

import numpy as np

NORTH_WEST, NORTH_EAST, SOUTH_WEST, SOUTH_EAST = (-1, -1), (-1, 1), (1, -1), (1, 1)
CORNERS = (NORTH_WEST, NORTH_EAST, SOUTH_WEST, SOUTH_EAST)
"""(row, column) side of each corner, in the order of :func:`corner_basis`."""
FILL_STEPS = 12
"""Newton steps at most; a thin sheet over strong relief takes the most."""
FILL_TOLERANCE = 1e-4
"""A cell whose offset moves less than this is done, m."""


def corner_basis(xp, k: int):
    """Weights of the four corners at the k x k pixel centres of a cell, (k * k, 4), float32."""
    f = (xp.arange(k, dtype=xp.float32) + 0.5) / k
    fy, fx = xp.meshgrid(f, f, indexing="ij")
    weights = xp.stack([(1 - fy) * (1 - fx), (1 - fy) * fx, fy * (1 - fx), fy * fx], axis=-1)
    return weights.reshape(-1, 4)


class Neighbours:
    """The kept cells as a flat list, and who stands next to whom.

    A map's work scales with the water, not with the bounding box: on the full extent the kept cells are an eighth of
    the grid. Arrays hold one entry per kept cell plus a last one, which stands for every cell left out.
    """

    def __init__(self, xp, keep: np.ndarray) -> None:
        self.xp = xp
        rows, cols = np.nonzero(keep)
        index = np.full(keep.shape, rows.size, np.int32)
        index[rows, cols] = np.arange(rows.size, dtype=np.int32)
        self.table = {
            (dj, di): xp.asarray(np.append(index[rows + dj, cols + di], rows.size))
            for dj in (-1, 0, 1)
            for di in (-1, 0, 1)
            if dj or di
        }

    def at(self, a, dj: int, di: int):
        """The value at (j + dj, i + di), for every cell."""
        return a[self.table[(dj, di)]]


def face_links(near, level, depth, wet, sill, axis: int, margin: float, ratio: float):
    """Whether a cell and its neighbour across the west (axis 1) or north (axis 0) face are one body of water."""
    xp = near.xp
    dj, di = (0, -1) if axis == 1 else (-1, 0)
    other_level = near.at(level, dj, di)
    other_depth = near.at(depth, dj, di)
    other_wet = near.at(wet, dj, di)
    face = sill + margin
    submerged = xp.minimum(level, other_level) > face
    reaches = xp.maximum(level, other_level) > face
    alike = xp.minimum(depth, other_depth) >= ratio * xp.maximum(depth, other_depth)
    return wet & other_wet & (submerged | (reaches & alike))


def corner_groups(near, lx, ly) -> list[tuple]:
    """For each corner, the masks of the neighbour across x, across y and on the diagonal that share the water."""
    groups = []
    for sy, sx in CORNERS:
        side_x = lx if sx < 0 else near.at(lx, 0, 1)
        side_y = ly if sy < 0 else near.at(ly, 1, 0)
        y_of_x = near.at(ly, 0 if sy < 0 else 1, sx)
        x_of_y = near.at(lx, sy, 0 if sx < 0 else 1)
        groups.append((side_x, side_y, (side_x & y_of_x) | (side_y & x_of_y)))
    return groups


def corner_means(near, value, weight, groups) -> list:
    """Each corner's mean of ``value`` over this cell and the neighbours that share the water there."""
    xp = near.xp
    w = weight.astype(xp.float32)
    held = value * w
    out = []
    for (sy, sx), (side_x, side_y, diagonal) in zip(CORNERS, groups, strict=True):
        across, along, corner = (near.at(held, 0, sx), near.at(held, sy, 0), near.at(held, sy, sx))
        total = held + across * side_x + along * side_y + corner * diagonal
        count = (
            w
            + near.at(w, 0, sx) * side_x
            + near.at(w, sy, 0) * side_y
            + near.at(w, sy, sx) * diagonal
        )
        out.append(xp.where(count > 0, total / xp.maximum(count, 1.0), value))
    return out


def at_pixels(xp, corners: list, cells, basis_t):
    """The surface at the pixels of the given cells: (n, 4) corner values times (4, k * k) weights."""
    return xp.stack([c[cells] for c in corners], axis=1) @ basis_t


def fill_cells(xp, surface, ground, mean_depth):
    """Pixel depth under a surface of this shape, raised or lowered until it holds the cell's water exactly.

    A level is the height of a flat fill, so on a slope with thin flow it stands well under the true surface. The
    water itself is known: the mean depth. The offset c of each cell solves ``sum(max(0, c - g)) = k * k * mean_depth``
    with g the ground over the surface shape. The left side is convex and piecewise linear, so Newton from above, where
    every pixel is wet, walks down onto the root and never past it. Deep cells stop at the first step, and work
    shrinks to the cells still moving, which is what keeps this cheap on the GPU.
    """
    relief = ground - surface
    pixels = relief.shape[1]
    water = mean_depth * pixels
    offset = relief.mean(axis=1) + mean_depth
    moving = xp.arange(relief.shape[0])
    left = relief
    for _ in range(FILL_STEPS):
        gap = offset[moving, None] - left
        under = gap > 0.0
        excess = (gap * under).sum(axis=1) - water[moving]
        step = excess / xp.maximum(under.sum(axis=1), 1).astype(xp.float32)
        offset[moving] = offset[moving] - step
        going = step > FILL_TOLERANCE
        if not bool(going.any()):
            break
        moving, left = moving[going], left[going]
    return xp.maximum(offset[:, None] - relief, 0.0)
