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
from wadi2d.basin.points import POINT_JOIN, POINT_REMOVE, PointEdit
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


def _nearest_node(surface: Surface, node: np.ndarray, edit: PointEdit, settings: BasinSettings) -> int:
    """The node an edit point lands on: the nearest within ``snap_m``, refused in words when there is none."""
    pixels = np.flatnonzero(node)
    x, y = surface.xy(pixels)
    distance = np.hypot(x - edit.x, y - edit.y)
    reach = max(settings.snap_m, surface.pixel)
    if pixels.size == 0 or distance.min() > reach:
        raise ValueError(f"{edit.kind} point {edit.name} lands on no junction within {reach:g} m: move it onto one")
    return int(pixels[np.argmin(distance)])


def _removed(
    surface: Surface, node: np.ndarray, pour: dict[int, PourPoint], edits: list[PointEdit], settings: BasinSettings
) -> list[int]:
    """The nodes the ``remove_junction`` points take out, each checked: a pour point or an outlet cannot go."""
    gone: list[int] = []
    for edit in (e for e in edits if e.kind == POINT_REMOVE):
        pixel = _nearest_node(surface, node, edit, settings)
        held = pour.get(pixel)
        if held is not None:
            raise ValueError(
                f"remove_junction point {edit.name} lands on {held.name}, a point of the job or of the layer: "
                "delete that point instead"
            )
        if surface.down[pixel] == NONE:
            raise ValueError(f"remove_junction point {edit.name} lands on an outlet of the network: an outlet stays")
        gone.append(pixel)
    return gone


def _next_node(down: np.ndarray, node: np.ndarray, pixel: int) -> int:
    """The first node on the way down from a pixel; NONE when the way ends without one."""
    while pixel != NONE and not node[pixel]:
        pixel = int(down[pixel])
    return pixel


def _end_nodes(surface: Surface, node: np.ndarray, bottoms: np.ndarray) -> np.ndarray:
    """The node each link drains to; a link ending at a removed node runs on to the next one."""
    end = np.where(node[bottoms], bottoms, surface.down[bottoms])
    for link in np.flatnonzero(~node[end]).tolist():
        end[link] = _next_node(surface.down, node, int(end[link]))
    return end


def _join_at(
    label: np.ndarray,
    end_node: np.ndarray,
    joined: dict[int, int],
    surface: Surface,
    node: np.ndarray,
    edits: list[PointEdit],
    settings: BasinSettings,
) -> np.ndarray:
    """One subbasin of the local subbasins at each ``join_subbasins`` point's node, HMS's merge; ``joined`` grows."""
    joins = [e for e in edits if e.kind == POINT_JOIN]
    if not joins:
        return label
    links = end_node.size
    pixels = np.bincount(label[label != NONE], minlength=links)
    for edit in joins:
        at = _nearest_node(surface, node, edit, settings)
        local = [link for link in np.flatnonzero(end_node == at).tolist() if link not in joined]
        if len(local) < 2:
            raise ValueError(
                f"join_subbasins point {edit.name}: its junction has {len(local)} local subbasin; nothing to join"
            )
        largest = max(local, key=lambda link: (pixels[link], -link))
        joined.update({link: largest for link in local if link != largest})
    table = np.arange(links, dtype=label.dtype)
    for link, target in joined.items():
        while target in joined:
            target = joined[target]
        table[link] = target
    kept = label != NONE
    label = label.copy()
    label[kept] = table[label[kept]]
    return label


def build_network(
    surface: Surface, pour: dict[int, PourPoint], settings: BasinSettings, edits: list[PointEdit] | None = None
) -> Network:
    """The network of a surface; ``edits`` are the Basin points layer's ``remove_junction`` and ``join_subbasins``."""
    edits = edits or []
    down, order, count = surface.down, surface.order, surface.count
    starts = np.fromiter(sorted(pour), dtype=np.int64, count=len(pour))
    stream = _streams(surface, settings, starts)
    if not stream.any():
        raise ValueError("no stream: lower the stream threshold or give a pour point")
    poured = np.zeros(down.size, dtype=bool)
    poured[starts] = True
    node = find_nodes(down, stream, poured)
    node[_removed(surface, node, pour, edits, settings)] = False
    link, tops, bottoms, above_top = trace_links(down, order, stream, node, count)
    end_node = _end_nodes(surface, node, bottoms)
    label, joined = _join_small(
        label_catchments(down, order, link), end_node, settings.min_subbasin_km2 / surface.km2_per_pixel
    )
    label = _join_at(label, end_node, joined, surface, node, edits, settings)
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
