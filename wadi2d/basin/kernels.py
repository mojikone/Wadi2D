"""The compiled core of the delineation: walks over a D8 raster held as flat receiver indices.

Interface: :func:`upstream_first`, :func:`accumulate`, :func:`mark_paths`, :func:`find_nodes`, :func:`trace_links`,
:func:`label_catchments`, :func:`above`, :func:`longest_paths`, :func:`path_to`. A pixel is its flat index, ``down[p]`` the
pixel it drains to, :data:`NONE` where it drains nowhere. Numba on plain arrays, so a raster of tens of millions of pixels
takes seconds.
"""

from __future__ import annotations

import math

import numpy as np
from numba import njit

NONE = -1
"""No receiver, no link, no label."""


@njit(cache=True)
def upstream_first(down: np.ndarray) -> np.ndarray:
    """Every pixel after all those draining into it. A shorter result than ``down`` means a cycle."""
    pending = np.zeros(down.size, dtype=np.int32)
    for receiver in down:
        if receiver != NONE:
            pending[receiver] += 1
    order = np.empty(down.size, dtype=np.int64)
    tail = 0
    for pixel in range(down.size):
        if pending[pixel] == 0:
            order[tail] = pixel
            tail += 1
    head = 0
    while head < tail:
        receiver = down[order[head]]
        head += 1
        if receiver != NONE:
            pending[receiver] -= 1
            if pending[receiver] == 0:
                order[tail] = receiver
                tail += 1
    return order[:tail]


@njit(cache=True)
def accumulate(down: np.ndarray, order: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Pixels draining through each pixel, itself included."""
    count = valid.astype(np.int64)
    for pixel in order:
        receiver = down[pixel]
        if receiver != NONE:
            count[receiver] += count[pixel]
    return count


@njit(cache=True)
def mark_paths(down: np.ndarray, stream: np.ndarray, starts: np.ndarray) -> None:
    """Add the path below each start to ``stream``, in place."""
    for start in starts:
        pixel = start
        while pixel != NONE and not stream[pixel]:
            stream[pixel] = True
            pixel = down[pixel]


@njit(cache=True)
def find_nodes(down: np.ndarray, stream: np.ndarray, poured: np.ndarray) -> np.ndarray:
    """Pour points, stream ends and confluences."""
    inflows = np.zeros(down.size, dtype=np.int32)
    node = poured & stream
    for pixel in range(down.size):
        if stream[pixel]:
            receiver = down[pixel]
            if receiver == NONE:
                node[pixel] = True
            else:
                inflows[receiver] += 1
    for pixel in range(down.size):
        if stream[pixel] and inflows[pixel] > 1:
            node[pixel] = True
    return node


@njit(cache=True)
def trace_links(
    down: np.ndarray, order: np.ndarray, stream: np.ndarray, node: np.ndarray, count: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Cut the streams at the nodes.

    A link runs from the pixel below a node, or a stream head, down to the next node. A node pixel closes the largest stream
    entering it, so the catchment above a node holds exactly the pixels counted at it; another stream entering stops one
    pixel short. Returns the link of each pixel, and per link its top pixel, its bottom pixel and the pixel above its top.
    """
    main = np.full(down.size, NONE, dtype=np.int64)
    for pixel in order:
        if stream[pixel]:
            receiver = down[pixel]
            if receiver != NONE:
                held = main[receiver]
                if (
                    held == NONE
                    or count[pixel] > count[held]
                    or (count[pixel] == count[held] and pixel < held)
                ):
                    main[receiver] = pixel
    link = np.full(down.size, NONE, dtype=np.int32)
    tops = np.empty(np.count_nonzero(stream), dtype=np.int64)
    bottoms = np.empty(tops.size, dtype=np.int64)
    above_top = np.empty(tops.size, dtype=np.int64)
    links = 0
    for pixel in order:
        if stream[pixel]:
            parent = main[pixel]
            if parent == NONE or node[parent]:
                link[pixel] = links
                tops[links] = pixel
                above_top[links] = parent
                bottoms[links] = pixel
                links += 1
            else:
                link[pixel] = link[parent]
                bottoms[link[pixel]] = pixel
    return link, tops[:links], bottoms[:links], above_top[:links]


@njit(cache=True)
def label_catchments(down: np.ndarray, order: np.ndarray, link: np.ndarray) -> np.ndarray:
    """Each pixel takes the first link on its way down; pixels that reach none stay :data:`NONE`."""
    label = link.copy()
    for index in range(order.size - 1, -1, -1):
        pixel = order[index]
        if label[pixel] == NONE and down[pixel] != NONE:
            label[pixel] = label[down[pixel]]
    return label


@njit(cache=True)
def above(down: np.ndarray, order: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """The seeds and every pixel whose way down passes through one."""
    reached = seeds.copy()
    for index in range(order.size - 1, -1, -1):
        pixel = order[index]
        if not reached[pixel] and down[pixel] != NONE:
            reached[pixel] = reached[down[pixel]]
    return reached


@njit(cache=True)
def longest_paths(
    down: np.ndarray, order: np.ndarray, label: np.ndarray, labels: int, nx: int, size: float
) -> tuple[np.ndarray, np.ndarray]:
    """Per label, the longest way along the D8 lines to where the label ends, m, and the pixel it starts from."""
    diagonal = size * math.sqrt(2.0)
    distance = np.zeros(down.size, dtype=np.float64)
    longest = np.zeros(labels, dtype=np.float64)
    start = np.full(labels, NONE, dtype=np.int64)
    for index in range(order.size - 1, -1, -1):
        pixel = order[index]
        name = label[pixel]
        if name != NONE:
            receiver = down[pixel]
            if receiver != NONE:
                step = size if abs(receiver - pixel) == 1 or abs(receiver - pixel) == nx else diagonal
                distance[pixel] = step + (distance[receiver] if label[receiver] == name else 0.0)
            if distance[pixel] >= longest[name]:
                longest[name] = distance[pixel]
                start[name] = pixel
    return longest, start


@njit(cache=True)
def path_to(down: np.ndarray, start: int, stop: int, nx: int, size: float) -> tuple[np.ndarray, np.ndarray]:
    """The pixels from ``start`` down to ``stop``, both kept, and the distance from ``start`` at each, m."""
    diagonal = size * math.sqrt(2.0)
    capacity = 1024
    pixels = np.empty(capacity, dtype=np.int64)
    distance = np.empty(capacity, dtype=np.float64)
    pixels[0], distance[0] = start, 0.0
    used = 1
    while pixels[used - 1] != stop:
        pixel = pixels[used - 1]
        receiver = down[pixel]
        if receiver == NONE:
            break
        if used == capacity:
            capacity *= 2
            pixels = np.concatenate((pixels, np.empty(used, dtype=np.int64)))
            distance = np.concatenate((distance, np.empty(used, dtype=np.float64)))
        step = size if abs(receiver - pixel) == 1 or abs(receiver - pixel) == nx else diagonal
        pixels[used], distance[used] = receiver, distance[used - 1] + step
        used += 1
    return pixels[:used], distance[:used]
