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

Filling a cell to its own water moves its surface by one number, which differs from the neighbour's and draws the cell as
a block, though the surface itself is continuous. So the offset is blended across each joined edge, in a band beside it,
and the cell refilled: see :func:`edge_basis`. Water stays exact, because the last fill sets it.
"""

from __future__ import annotations

import numpy as np

NORTH_WEST, NORTH_EAST, SOUTH_WEST, SOUTH_EAST = (-1, -1), (-1, 1), (1, -1), (1, 1)
CORNERS = (NORTH_WEST, NORTH_EAST, SOUTH_WEST, SOUTH_EAST)
"""(row, column) side of each corner, in the order of :func:`corner_basis`."""
AROUND = tuple((dj, di) for dj in (-1, 0, 1) for di in (-1, 0, 1))
"""(row, column) of a cell and its eight neighbours, in the order of :func:`edge_basis`."""
OWN = (0, 0)
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


def edge_basis(xp, k: int, band: float):
    """Weights of a cell and its eight neighbours at the k x k pixel centres of a cell, (k * k, 9), float32.

    A pixel further than ``band`` of a cell from every edge reads its own cell alone. Nearer, it eases to half and half at
    the edge, so two cells read the same value there. A band and not a wide kernel, because a wide one barely moves a
    checkerboard of offsets: the cell's own share of its mean is what makes the refill converge, 0.72 at a band of 0.3
    against 0.44 for a quadratic spline.
    """
    f = (xp.arange(k, dtype=xp.float32) + 0.5) / k
    x = xp.clip(xp.minimum(f, 1.0 - f) / band, 0.0, 1.0)
    own = 0.5 + 0.5 * x * x * (3.0 - 2.0 * x)
    other = 1.0 - own
    along = xp.stack([other * (f < 0.5), own, other * (f >= 0.5)])  # the cell before, this one, the cell after
    weights = [xp.outer(along[dj + 1], along[di + 1]).ravel() for dj, di in AROUND]
    return xp.stack(weights, axis=-1).astype(xp.float32)


class Neighbours:
    """The kept cells as a flat list, and who stands next to whom.

    A map's work scales with the water, not with the bounding box: on the full extent the kept cells are an eighth of
    the grid. Arrays hold one entry per kept cell plus a last one, which stands for every cell left out.
    """

    def __init__(self, xp, keep: np.ndarray, order: tuple[np.ndarray, np.ndarray] | None = None) -> None:
        """``order`` lists the cells when they must stand in another order than ``keep``'s."""
        self.xp = xp
        rows, cols = np.nonzero(keep) if order is None else order
        index = np.full((keep.shape[0] + 2, keep.shape[1] + 2), rows.size, np.int32)
        rows, cols = rows + 1, cols + 1  # a margin, because on a coarse lattice a kept cell can touch the edge
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


def face_joins(near, level, depth, wet, sill, axis: int, margin: float, ratio: float):
    """Whether the cells either side of the west (axis 1) or north (axis 0) face of each cell share their corners
    on the continuous surface (W100): water passes the face, a wet cell's level standing above its ground (crest lines
    and walls included, so the surface is never carried over high ground), and the two are one body of water there.

    One body: both levels stand above the face (a pool, a submerged bank); or the water steps down the face between
    depths alike (``ratio``), one flow down a slope steeper than the cells; or it spills into a dry cell, which then
    takes the water to where its ground rises through it. A step from water of another depth is a brink, a film
    over a bank into a channel or a pool over a crest, and both keep their own surface there: tried with the two
    joined and the levels weighted by depth (RAS Mapper's depth-weighted faces), the film's cell took the channel's
    level at its brink, plunged, and its fill lifted its other neighbour's surface by 17 cm on a flat bank top.
    :func:`face_links` is W9's test, without the dry cell."""
    xp = near.xp
    dj, di = (0, -1) if axis == 1 else (-1, 0)
    face = sill + margin
    other_level, other_depth, other_wet = near.at(level, dj, di), near.at(depth, dj, di), near.at(wet, dj, di)
    passes = (wet & (level > face)) | (other_wet & (other_level > face))
    submerged = wet & other_wet & (xp.minimum(level, other_level) > face)
    alike = xp.minimum(depth, other_depth) >= ratio * xp.maximum(depth, other_depth)
    return passes & (submerged | alike | ~wet | ~other_wet)


def touched(near, groups):
    """Cells that share a corner with another: a dry one among them takes pixels, so water spilling into it ends on
    its ground and not at the cell edge."""
    xp = near.xp
    out = None
    for side_x, side_y, diagonal in groups:
        some = side_x | side_y | diagonal
        out = some if out is None else (out | some)
    return out if out is not None else xp.zeros(0, bool)


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


def corner_components(near, lx, ly) -> list[tuple]:
    """:func:`corner_groups` with every path round the corner (W100): the four cells there are four faces in a ring,
    and a neighbour beside the cell also shares the water when it is reached the long way round, through the other two.
    Without that, two joined cells read different values at a corner they share a quarter of the time on random
    ground, and the surface steps along their edge."""
    groups = []
    for sy, sx in CORNERS:
        a = lx if sx < 0 else near.at(lx, 0, 1)  # the cell and its neighbour across x
        b = ly if sy < 0 else near.at(ly, 1, 0)  # the cell and its neighbour across y
        c = near.at(ly, 0 if sy < 0 else 1, sx)  # the neighbour across x and the diagonal
        e = near.at(lx, sy, 0 if sx < 0 else 1)  # the neighbour across y and the diagonal
        groups.append((a | (b & e & c), b | (a & c & e), (a & c) | (b & e)))
    return groups


def corner_sills(near, lx, ly, sill_x, sill_y) -> list:
    """For each corner, the lowest ground of the four faces that meet there and that water does not pass; infinite
    where it passes all four (W100). The same number for every cell round the corner."""
    xp = near.xp
    out = []
    for sy, sx in CORNERS:
        a = (lx, sill_x) if sx < 0 else (near.at(lx, 0, 1), near.at(sill_x, 0, 1))
        b = (ly, sill_y) if sy < 0 else (near.at(ly, 1, 0), near.at(sill_y, 1, 0))
        c = (near.at(ly, 0 if sy < 0 else 1, sx), near.at(sill_y, 0 if sy < 0 else 1, sx))
        e = (near.at(lx, sy, 0 if sx < 0 else 1), near.at(sill_x, sy, 0 if sx < 0 else 1))
        lowest = None
        for joined, ground in (a, b, c, e):
            here = xp.where(joined, xp.inf, ground)
            lowest = here if lowest is None else xp.minimum(lowest, here)
        out.append(lowest)
    return out


def capped_moves(levels: list, moves: list, sills: list, xp) -> list:
    """Each corner's level plus the move that holds its cells' water, the move kept from lifting the surface over
    the lowest face round the corner that water does not pass (W100): a thin sheet spread over its cell stops short
    of a face its cell's water never crosses, instead of meeting it in a straight line at the cell edge."""
    out = []
    for level, move, sill in zip(levels, moves, sills, strict=True):
        room = xp.maximum(sill - level, 0.0)
        out.append(level + xp.minimum(move, room))
    return out


def around_links(groups) -> dict:
    """Which neighbours share the water with a cell, per entry of ``AROUND``, from :func:`corner_groups`."""
    links = {}
    for (sy, sx), (side_x, side_y, diagonal) in zip(CORNERS, groups, strict=True):
        links[(0, sx)], links[(sy, 0)], links[(sy, sx)] = side_x, side_y, diagonal
    return links


def offsets_around(near, offset, links) -> list:
    """The nine offsets a cell's pixels read: its own, and a neighbour's where the two share the water."""
    xp = near.xp
    return [offset if key == OWN else xp.where(links[key], near.at(offset, *key), offset) for key in AROUND]


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


def weighted_corner_means(near, value, weight, groups) -> list:
    """:func:`corner_means` with weights of any size (W100): there the count of cells is at least one wherever it is
    not zero, here a weight of a few centimetres squared is divided by itself."""
    xp = near.xp
    w = weight.astype(xp.float32)
    held = value * w
    out = []
    for (sy, sx), (side_x, side_y, diagonal) in zip(CORNERS, groups, strict=True):
        across, along, corner = (near.at(held, 0, sx), near.at(held, sy, 0), near.at(held, sy, sx))
        total = held + across * side_x + along * side_y + corner * diagonal
        count = w + near.at(w, 0, sx) * side_x + near.at(w, sy, 0) * side_y + near.at(w, sy, sx) * diagonal
        some = count > 0.0
        out.append(xp.where(some, total / xp.where(some, count, 1.0), value))
    return out


def at_pixels(xp, corners: list, cells, basis_t):
    """The surface at the pixels of the given cells: (n, 4) corner values times (4, k * k) weights."""
    return xp.stack([c[cells] for c in corners], axis=1) @ basis_t


def fill_offset(xp, surface, ground, mean_depth):
    """How far a surface of this shape must move, per cell, to hold the cell's water exactly.

    A level is the height of a flat fill, so on a slope with thin flow it stands well under the true surface. The
    water itself is known: the mean depth. The offset c of each cell solves ``sum(max(0, c - g)) = k * k * mean_depth``
    with g the ground over the surface shape. The left side is convex and piecewise linear, so Newton from above, where
    every pixel is wet, walks down onto the root and never past it. Deep cells stop at the first step, and work
    shrinks to the cells still moving, which is what keeps this cheap on the GPU.
    """
    return _fill(xp, ground - surface, mean_depth)


def _fill(xp, relief, mean_depth):
    """:func:`fill_offset` on the ground over the surface. On the card one kernel a Newton step (W93), the same
    numbers to the digit."""
    if xp is not np:
        from wadi2d.products.fill_kernels import newton_card

        return newton_card(xp, relief, mean_depth, FILL_STEPS, FILL_TOLERANCE)
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
    return offset


def fill_cells(xp, surface, ground, mean_depth):
    """Pixel depth under a surface of this shape, moved until it holds the cell's water exactly."""
    relief = ground - surface
    offset = _fill(xp, relief, mean_depth)
    return xp.maximum(offset[:, None] - relief, 0.0)
