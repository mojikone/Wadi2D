"""MeshKernel helpers shared by the W44 scripts: GeometryList builders, Mesh2d <-> numpy, orthogonality measures."""

from __future__ import annotations

import numpy as np
import shapely
from meshkernel import GeometryList, Mesh2d

SEP = -999.0
INNER = -998.0
MISSING = -999.0


def geom_list(parts: list[np.ndarray], closed: bool = False) -> GeometryList:
    """Several polylines (or polygons, when closed) as one GeometryList separated by -999."""
    xs, ys = [], []
    for i, p in enumerate(parts):
        p = np.asarray(p, float)
        if closed and not np.allclose(p[0], p[-1]):
            p = np.vstack([p, p[:1]])
        if i:
            xs.append(SEP)
            ys.append(SEP)
        xs.extend(p[:, 0])
        ys.extend(p[:, 1])
    return GeometryList(np.asarray(xs, float), np.asarray(ys, float))


def polygon_geom(poly: shapely.Polygon) -> GeometryList:
    """A shapely polygon with holes as a MeshKernel GeometryList (outer ring, then each hole after -998)."""
    xs, ys = [], []
    ext = np.asarray(poly.exterior.coords)
    xs.extend(ext[:, 0])
    ys.extend(ext[:, 1])
    for ring in poly.interiors:
        r = np.asarray(ring.coords)
        xs.append(INNER)
        ys.append(INNER)
        xs.extend(r[:, 0])
        ys.extend(r[:, 1])
    return GeometryList(np.asarray(xs, float), np.asarray(ys, float))


def multipolygon_geom(polys: list[shapely.Polygon]) -> GeometryList:
    xs, ys = [], []
    for i, poly in enumerate(polys):
        if i:
            xs.append(SEP)
            ys.append(SEP)
        g = polygon_geom(poly)
        xs.extend(g.x_coordinates)
        ys.extend(g.y_coordinates)
    return GeometryList(np.asarray(xs, float), np.asarray(ys, float))


def faces_table(m: Mesh2d) -> tuple[np.ndarray, np.ndarray]:
    """face_nodes as a padded (n_faces, max_nodes) int array with -1 padding, and nodes_per_face."""
    npf = np.asarray(m.nodes_per_face, dtype=np.int64)
    fn = np.asarray(m.face_nodes, dtype=np.int64)
    if len(npf) == 0:
        return np.zeros((0, 4), np.int64), npf
    width = int(npf.max())
    table = np.full((len(npf), width), -1, np.int64)
    starts = np.concatenate([[0], np.cumsum(npf)[:-1]])
    for k in range(width):
        sel = npf > k
        table[sel, k] = fn[starts[sel] + k]
    return table, npf


def face_polygons(m: Mesh2d) -> np.ndarray:
    """Shapely polygons of every face."""
    table, npf = faces_table(m)
    x = np.asarray(m.node_x)
    y = np.asarray(m.node_y)
    polys = []
    for row, n in zip(table, npf):
        idx = row[:n]
        polys.append(shapely.Polygon(np.column_stack([x[idx], y[idx]])))
    return np.asarray(polys, dtype=object)


def face_geometry(m: Mesh2d) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Signed area (positive counter-clockwise), centroid x and y of every face, vectorised over the padded table."""
    table, npf = faces_table(m)
    x = np.asarray(m.node_x)
    y = np.asarray(m.node_y)
    width = table.shape[1]
    # ring with the next node: the node after the last real one is the first
    nxt = np.roll(table, -1, axis=1)
    last = np.arange(width)[None, :] == (npf[:, None] - 1)
    nxt = np.where(last, table[:, :1], nxt)
    valid = table >= 0
    i0 = np.where(valid, table, 0)
    i1 = np.where(valid, nxt, 0)
    # local coordinates about the first node of each face: at UTM magnitudes (y about 2.7e6) the raw shoelace
    # sums cancel to 1e-7 of their terms and the centroid lands 0.2 m off
    ox = x[table[:, 0]][:, None]
    oy = y[table[:, 0]][:, None]
    x0 = x[i0] - ox
    y0 = y[i0] - oy
    x1 = x[i1] - ox
    y1 = y[i1] - oy
    cross = x0 * y1 - x1 * y0
    cross = np.where(valid, cross, 0.0)
    a2 = cross.sum(axis=1)
    area = 0.5 * a2
    safe = np.where(np.abs(a2) < 1e-12, np.nan, a2)
    cx = np.where(valid, (x0 + x1) * cross, 0.0).sum(axis=1) / (3.0 * safe) + ox[:, 0]
    cy = np.where(valid, (y0 + y1) * cross, 0.0).sum(axis=1) / (3.0 * safe) + oy[:, 0]
    mean_x = np.where(valid, x[i0], 0.0).sum(axis=1) / npf
    mean_y = np.where(valid, y[i0], 0.0).sum(axis=1) / npf
    cx = np.where(np.isfinite(cx), cx, mean_x)
    cy = np.where(np.isfinite(cy), cy, mean_y)
    return area, cx, cy


def face_areas(m: Mesh2d) -> np.ndarray:
    return np.abs(face_geometry(m)[0])


def topology(m: Mesh2d) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Edges and edge-face adjacency built from the face table alone (MeshKernel's edge_faces is not relied on).

    Returns edge_nodes (n_edges, 2) with the lower node first, edge_faces (n_edges, 2) with -1 where there is no
    second face, and face_edges padded with -1 like the face table."""
    table, npf = faces_table(m)
    width = table.shape[1]
    nxt = np.roll(table, -1, axis=1)
    last = np.arange(width)[None, :] == (npf[:, None] - 1)
    nxt = np.where(last, table[:, :1], nxt)
    valid = table >= 0
    a = np.where(valid, table, -1)
    b = np.where(valid, nxt, -1)
    lo = np.minimum(a, b)
    hi = np.maximum(a, b)
    fidx = np.repeat(np.arange(len(npf))[:, None], width, axis=1)
    sel = valid.ravel()
    pairs = np.column_stack([lo.ravel()[sel], hi.ravel()[sel]])
    faces = fidx.ravel()[sel]
    key = pairs[:, 0].astype(np.int64) * (int(pairs.max()) + 2) + pairs[:, 1]
    uniq, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
    edge_nodes = np.zeros((len(uniq), 2), np.int64)
    edge_nodes[inv] = pairs
    edge_faces = np.full((len(uniq), 2), -1, np.int64)
    order = np.argsort(inv, kind="stable")
    inv_sorted = inv[order]
    faces_sorted = faces[order]
    first = np.concatenate([[True], inv_sorted[1:] != inv_sorted[:-1]])
    edge_faces[inv_sorted[first], 0] = faces_sorted[first]
    second = ~first
    edge_faces[inv_sorted[second], 1] = faces_sorted[second]
    if counts.max() > 2:
        raise ValueError(f"{int((counts > 2).sum())} edges shared by more than two faces")
    face_edges = np.full(table.shape, -1, np.int64)
    face_edges[valid] = inv
    return edge_nodes, edge_faces, face_edges


def centroid_orthogonality(m: Mesh2d) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Wadi2D's own sense: for each interior edge, |cos| of the angle between the edge and the line joining the
    two face centroids (0 is orthogonal), and the offset of that line's crossing from the edge midpoint over the
    edge length (0 is centred). Returns (ortho, offset, interior mask), in the order of topology()."""
    x = np.asarray(m.node_x)
    y = np.asarray(m.node_y)
    en, ef, _ = topology(m)
    _, cx, cy = face_geometry(m)
    interior = (ef[:, 0] >= 0) & (ef[:, 1] >= 0)
    ex = x[en[:, 1]] - x[en[:, 0]]
    ey = y[en[:, 1]] - y[en[:, 0]]
    el = np.hypot(ex, ey)
    f0 = np.where(interior, ef[:, 0], 0)
    f1 = np.where(interior, ef[:, 1], 0)
    dx = cx[f1] - cx[f0]
    dy = cy[f1] - cy[f0]
    dl = np.hypot(dx, dy)
    ortho = np.abs(ex * dx + ey * dy) / np.maximum(el * dl, 1e-12)
    denom = ex * dy - ey * dx
    px0 = x[en[:, 0]]
    py0 = y[en[:, 0]]
    t = ((cx[f0] - px0) * dy - (cy[f0] - py0) * dx) / np.where(np.abs(denom) < 1e-12, np.nan, denom)
    offset = np.abs(t - 0.5)
    ortho[~interior] = np.nan
    offset[~interior] = np.nan
    return ortho, offset, interior


def mesh_from_faces(node_xy: np.ndarray, faces: list[np.ndarray] | np.ndarray) -> Mesh2d:
    """A Mesh2d from node coordinates and a list of node-index rings (any polygon size); edges built here."""
    node_xy = np.asarray(node_xy, float)
    rings = [np.asarray(f, np.int64) for f in faces]
    npf = np.array([len(r) for r in rings], np.int32)
    fn = np.concatenate(rings).astype(np.int32) if rings else np.zeros(0, np.int32)
    m = Mesh2d(node_x=node_xy[:, 0].copy(), node_y=node_xy[:, 1].copy(), face_nodes=fn, nodes_per_face=npf)
    en, _, _ = topology(m)
    m.edge_nodes = en.astype(np.int32).ravel()
    return m


def mesh_from_curvilinear(x: np.ndarray, y: np.ndarray) -> tuple[Mesh2d, np.ndarray]:
    """A quad mesh from an (n, m) node array with NaN holes; returns the mesh and the (n, m) node index map."""
    valid = np.isfinite(x) & np.isfinite(y)
    idx = np.full(x.shape, -1, np.int64)
    idx[valid] = np.arange(valid.sum())
    node_xy = np.column_stack([x[valid], y[valid]])
    n, mm = x.shape
    i, j = np.meshgrid(np.arange(n - 1), np.arange(mm - 1), indexing="ij")
    q = np.stack([idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]], axis=-1).reshape(-1, 4)
    q = q[(q >= 0).all(axis=1)]
    # orient counter-clockwise
    px = node_xy[q, 0]
    py = node_xy[q, 1]
    a2 = (px * np.roll(py, -1, axis=1) - np.roll(px, -1, axis=1) * py).sum(axis=1)
    q[a2 < 0] = q[a2 < 0][:, ::-1]
    return mesh_from_faces(node_xy, list(q)), idx


def mesh_summary(m: Mesh2d) -> dict:
    npf = np.asarray(m.nodes_per_face)
    from collections import Counter

    return {
        "nodes": int(len(m.node_x)),
        "edges": int(len(m.edge_nodes) // 2),
        "faces": int(len(npf)),
        "faces_by_nodes": {int(k): int(v) for k, v in sorted(Counter(npf.tolist()).items())},
    }


def mk_orthogonality(mk) -> np.ndarray:
    """MeshKernel's own per-edge orthogonality, NaN where it reports its missing value (boundary edges)."""
    g = mk.mesh2d_get_orthogonality()
    v = np.asarray(g.values, float)
    v = np.where(v <= -998.0, np.nan, v)
    return v


def shares(v: np.ndarray) -> dict:
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return {"n": 0}
    return {
        "n": int(len(v)),
        "median": float(np.median(v)),
        "p90": float(np.percentile(v, 90)),
        "p99": float(np.percentile(v, 99)),
        "max": float(v.max()),
        "share_gt_0.01": float((v > 0.01).mean()),
        "share_gt_0.02": float((v > 0.02).mean()),
        "share_gt_0.05": float((v > 0.05).mean()),
    }


def save_mesh(path, m: Mesh2d, **extra) -> None:
    table, npf = faces_table(m)
    np.savez_compressed(
        path,
        node_x=np.asarray(m.node_x),
        node_y=np.asarray(m.node_y),
        edge_nodes=np.asarray(m.edge_nodes, np.int64).reshape(-1, 2),
        face_nodes=table,
        nodes_per_face=npf,
        edge_faces=np.asarray(m.edge_faces, np.int64).reshape(-1, 2),
        face_edges=np.asarray(m.face_edges, np.int64),
        **extra,
    )


def load_mesh(path) -> tuple[Mesh2d, dict]:
    d = np.load(path, allow_pickle=False)
    table = d["face_nodes"]
    npf = d["nodes_per_face"]
    fn = np.concatenate([row[:n] for row, n in zip(table, npf)]) if len(npf) else np.zeros(0, np.int64)
    m = Mesh2d(
        node_x=d["node_x"].astype(float),
        node_y=d["node_y"].astype(float),
        edge_nodes=d["edge_nodes"].astype(np.int32).ravel(),
        face_nodes=fn.astype(np.int32),
        nodes_per_face=npf.astype(np.int32),
    )
    extra = {k: d[k] for k in d.files if k not in ("node_x", "node_y", "edge_nodes", "face_nodes", "nodes_per_face", "edge_faces", "face_edges")}
    return m, extra
