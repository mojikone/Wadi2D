"""The water surface inside a cell, from the levels of the cells around it.

A cell holds one level, so on a slope a flat surface reads high at the low end of each cell. Here a surface slopes
through its cell corners, and a corner takes the mean of the cells that are one body of water there. Whether two
cells are one body of water is decided at their shared face, from the ground of that face (the sub-grid face invert,
crest lines and walls included) and not from a fixed jump in level, so it follows connected flow at any slope:

- submerged: both levels stand above the face;
- stepping: the higher level stands above the face and the two depths are alike, which is one flow going down a
  slope steeper than the cells can follow. A hill sheet or a shallow steep channel is this; a thin film on a bank
  beside a deep channel is not.

Anything else keeps its own level, so a surface is never carried over a bank. ``xp`` is NumPy or CuPy: one source
for both backends, in float32.
"""

from __future__ import annotations

NORTH_WEST, NORTH_EAST, SOUTH_WEST, SOUTH_EAST = (-1, -1), (-1, 1), (1, -1), (1, 1)
CORNERS = (NORTH_WEST, NORTH_EAST, SOUTH_WEST, SOUTH_EAST)
"""(row, column) side of each corner, in the order of :func:`corner_basis`."""


def corner_basis(xp, k: int):
    """Weights of the four corners at the k x k pixel centres of a cell, (k * k, 4), float32."""
    f = (xp.arange(k, dtype=xp.float32) + 0.5) / k
    fy, fx = xp.meshgrid(f, f, indexing="ij")
    weights = xp.stack([(1 - fy) * (1 - fx), (1 - fy) * fx, fy * (1 - fx), fy * fx], axis=-1)
    return weights.reshape(-1, 4)


def at(xp, a, dj: int, di: int):
    """The value at (j + dj, i + di), for every cell. The grid's edge is never active, so wrapping is harmless."""
    return xp.roll(a, (-dj, -di), axis=(0, 1))


def face_links(xp, level, depth, wet, sill, axis: int, margin: float, ratio: float):
    """Whether a cell and its neighbour across the west (axis 1) or north (axis 0) face are one body of water."""
    other_level = xp.roll(level, 1, axis=axis)
    other_depth = xp.roll(depth, 1, axis=axis)
    other_wet = xp.roll(wet, 1, axis=axis)
    face = sill + margin
    submerged = xp.minimum(level, other_level) > face
    reaches = xp.maximum(level, other_level) > face
    alike = xp.minimum(depth, other_depth) >= ratio * xp.maximum(depth, other_depth)
    return wet & other_wet & (submerged | (reaches & alike))


def corner_groups(xp, lx, ly) -> list[tuple]:
    """For each corner, the masks of the neighbour across x, across y and on the diagonal that share the water."""
    groups = []
    for sy, sx in CORNERS:
        side_x = lx if sx < 0 else at(xp, lx, 0, 1)
        side_y = ly if sy < 0 else at(xp, ly, 1, 0)
        y_of_x = at(xp, ly, 0 if sy < 0 else 1, sx)
        x_of_y = at(xp, lx, sy, 0 if sx < 0 else 1)
        groups.append((side_x, side_y, (side_x & y_of_x) | (side_y & x_of_y)))
    return groups


def corner_means(xp, value, weight, groups) -> list:
    """Each corner's mean of ``value`` over this cell and the neighbours that share the water there."""
    w = weight.astype(xp.float32)
    held = value * w
    out = []
    for (sy, sx), (side_x, side_y, diagonal) in zip(CORNERS, groups, strict=True):
        total = (
            held
            + at(xp, held, 0, sx) * side_x
            + at(xp, held, sy, 0) * side_y
            + at(xp, held, sy, sx) * diagonal
        )
        count = w + at(xp, w, 0, sx) * side_x + at(xp, w, sy, 0) * side_y + at(xp, w, sy, sx) * diagonal
        out.append(xp.where(count > 0, total / xp.maximum(count, 1.0), value))
    return out


def at_pixels(xp, corners: list, rows, cols, basis_t):
    """The surface at the pixels of the given cells: (n, 4) corner values times (4, k * k) weights."""
    return xp.stack([c[rows, cols] for c in corners], axis=1) @ basis_t


def fill_cells(xp, surface, ground, mean_depth):
    """Pixel depth under a surface of this shape, raised or lowered until it holds the cell's water exactly.

    A level is the height of a flat fill, so on a slope with thin flow it stands well under the true surface. The
    water itself is known: the mean depth. The offset of each cell solves ``sum(max(0, c - g)) = k * k * mean_depth``
    with g the ground over the surface shape, by the sorted fill the table builder also uses.
    """
    relief = ground - surface
    n = relief.shape[1]
    ordered = xp.sort(relief, axis=1)
    held = xp.cumsum(ordered, axis=1)
    count = xp.arange(1, n + 1, dtype=xp.float32)
    needed = count[None, :] * ordered - held
    water = (mean_depth * n)[:, None]
    wet_pixels = xp.maximum((needed <= water).sum(axis=1), 1)
    picked = held[xp.arange(ordered.shape[0]), wet_pixels - 1]
    offset = (water[:, 0] + picked) / wet_pixels.astype(xp.float32)
    return xp.maximum(offset[:, None] - relief, 0.0)
