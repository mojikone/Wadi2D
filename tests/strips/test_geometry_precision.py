"""Cell areas and centroids on map coordinates (W52): the shoelace on UTM values cancelled to metres of error in a
small cell's centroid, which broke the centre mesh at 5 m."""

from __future__ import annotations

import numpy as np


def test_a_small_cell_on_map_coordinates_has_its_true_centroid() -> None:
    """The shoelace on UTM coordinates cancelled to metres in a small cell (W52): taken from the ring's first node
    it is exact. Both copies, the geometry's and the centre generator's."""
    from wadi2d.strips.centres import _areas_centroids
    from wadi2d.strips.geometry import MeshGeometry

    x0, y0 = 612_345.678, 2_634_567.891
    ring = np.array([[0.0, 0.0], [3.25, 0.0], [3.25, 20.0], [0.0, 20.0]]) @ np.array([[np.cos(1.0), np.sin(1.0)], [-np.sin(1.0), np.cos(1.0)]]) + [x0, y0]
    want = ring.mean(axis=0)
    geo = MeshGeometry.from_rings(ring[:, 0], ring[:, 1], [np.arange(4)])
    area, cx, cy = geo.areas_centroids()
    assert abs(area[0] - 65.0) < 1e-6 and np.hypot(cx[0] - want[0], cy[0] - want[1]) < 1e-6
    area2, cen = _areas_centroids(ring, [np.arange(4)])
    assert abs(area2[0] - 65.0) < 1e-6 and np.hypot(*(cen[0] - want)) < 1e-6
