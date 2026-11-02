"""From a D8 raster and pour points to links, nodes and catchments.

A stream is every pixel draining the threshold area, plus the way down from every pour point. A node is a pour point, a
confluence or the end of a stream. Each link is cut from one node to the next, and every pixel takes the first link on its
way down, so the subbasins above a node hold exactly the pixels counted at that node.

Interface: :class:`Network`, :func:`build_network`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.basin.delineate import Surface
from wadi2d.basin.kernels import NONE, find_nodes, label_catchments, mark_paths, trace_links
from wadi2d.basin.pour import PourPoint, stream_limit
from wadi2d.config.schema import BasinSettings


@dataclass
class Network:
    """Links by id; a pixel's ``label`` is the link whose subbasin holds it."""

    label: np.ndarray
    tops: np.ndarray
    bottoms: np.ndarray
    start_node: np.ndarray
    """The node above each link, NONE at a stream head."""
    end_node: np.ndarray
    """The node each link drains to."""
    nodes: np.ndarray
    """Node pixels, largest drainage area first."""
    pour: dict[int, PourPoint]
    subbasins: np.ndarray
    """The links that keep a subbasin, largest drainage area first."""
    joined: dict[int, int]
    """A link whose local catchment went to a neighbour: link to the neighbour."""


def _streams(surface: Surface, settings: BasinSettings, starts: np.ndarray) -> np.ndarray:
    limit = stream_limit(surface, settings)
    stream = np.zeros(surface.down.size, dtype=bool) if limit is None else surface.count >= limit
    mark_paths(surface.down, stream, starts)
    return stream


def _join_small(label: np.ndarray, end_node: np.ndarray, limit: float) -> tuple[np.ndarray, dict[int, int]]:
    """Give a local catchment under ``limit`` pixels to the largest neighbour draining to the same node.

    Nothing above any node changes: both drain to that node, and neither reaches any other first.
    """
    links = end_node.size
    pixels = np.bincount(label[label != NONE], minlength=links)
    largest: dict[int, int] = {}
    for link in range(links):
        node = int(end_node[link])
        if node not in largest or pixels[link] > pixels[largest[node]]:
            largest[node] = link
    joined = {
        link: largest[int(end_node[link])]
        for link in range(links)
        if pixels[link] < limit
        and largest[int(end_node[link])] != link
        and pixels[largest[int(end_node[link])]] >= limit
    }
    if joined:
        table = np.arange(links, dtype=label.dtype)
        table[list(joined)] = list(joined.values())
        kept = label != NONE
        label = label.copy()
        label[kept] = table[label[kept]]
    return label, joined


def build_network(surface: Surface, pour: dict[int, PourPoint], settings: BasinSettings) -> Network:
    """The network of a surface."""
    down, order, count = surface.down, surface.order, surface.count
    starts = np.fromiter(sorted(pour), dtype=np.int64, count=len(pour))
    stream = _streams(surface, settings, starts)
    if not stream.any():
        raise ValueError("no stream: lower the stream threshold or give a pour point")
    poured = np.zeros(down.size, dtype=bool)
    poured[starts] = True
    node = find_nodes(down, stream, poured)
    link, tops, bottoms, above_top = trace_links(down, order, stream, node, count)
    label, joined = _join_small(
        label_catchments(down, order, link),
        np.where(node[bottoms], bottoms, down[bottoms]),
        settings.min_subbasin_km2 / surface.km2_per_pixel,
    )
    end_node = np.where(node[bottoms], bottoms, down[bottoms])
    pixels = np.flatnonzero(node)
    keep = np.setdiff1d(np.arange(tops.size), np.fromiter(joined, dtype=np.int64, count=len(joined)))
    return Network(
        label,
        tops,
        bottoms,
        above_top,
        end_node,
        pixels[np.lexsort((pixels, -count[pixels]))],
        pour,
        keep[np.lexsort((bottoms[keep], -count[bottoms[keep]]))],
        joined,
    )
