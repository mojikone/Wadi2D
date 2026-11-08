"""The idea sketch for his zoom window (2026-11-07): cell centres instead of rings. Lattice centres away from the
streams, rows of centres along the 1 km2 thalwegs inside a floor of height above the thalweg (HAND) under 2 m, and
the mesh is the Voronoi diagram of the centres, which is how HEC-RAS builds its cells: squares where the centres are
a lattice, aligned quads along the stream with the thalweg on a face, polygons of five to seven faces in between,
no triangle. Small inner-bend cells are merged by dropping their centres; the lattice centres of the transition
band are relaxed towards their cell's centroid; cells over eight faces (HEC-RAS's limit) are counted. Geometry
only, nothing of it is in the engine."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np
import rasterio
import shapely
from rasterio import features
from rasterio.windows import from_bounds
from scipy import ndimage
from scipy.spatial import Voronoi, cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zoom_floor_check import DEM, MESH, hillshade, read  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402

WORK = Path(__file__).resolve().parent / "stream_corridors"
BOX = (437550.0, 2709422.0, 439905.0, 2711262.0)
DETAIL = (438140.0, 2709940.0, 438640.0, 2710440.0)
DX = 30.0
HAND_FLOOR = 2.0
REACH = 300.0
MIN_KM2 = 3.0
SMALL = 0.4 * DX * DX
"""A cell under this area is merged into its neighbours by dropping its centre."""
MAX_FACES = 8
"""HEC-RAS's limit on faces per cell."""
NEAR = 0.7 * DX
"""A lattice centre this close to a corridor centre goes, else a sliver forms between them."""
BAND = 1.5 * DX
RELAX_ROUNDS = 2
MERGE_ROUNDS = 3


def floor_polygon(z: np.ndarray, tr, thalwegs: list[dict]) -> tuple[shapely.Geometry, np.ndarray]:
    """The floor as the ground under HAND_FLOOR above the nearest thalweg sample within REACH of a stream, the
    components touching a stream, specks dropped; and the HAND field itself."""
    px = tr.a
    gx0, gy0 = tr.c, tr.f
    pts = np.vstack([shapely.get_coordinates(shapely.line_interpolate_point(t["geometry"], np.arange(0.0, t["geometry"].length, 5.0))) for t in thalwegs])
    c = (pts[:, 0] - gx0) / px
    r = (gy0 - pts[:, 1]) / px
    zt = ndimage.map_coordinates(z, [r, c], order=1, mode="nearest")
    rows, cols = np.indices(z.shape)
    gxy = np.column_stack(((cols.ravel() + 0.5) * px + gx0, gy0 - (rows.ravel() + 0.5) * px))
    d, k = cKDTree(pts).query(gxy)
    hand = (z.ravel() - zt[k]).reshape(z.shape)
    floor = (hand < HAND_FLOOR) & (d.reshape(z.shape) < REACH)
    floor = ndimage.binary_opening(floor, iterations=1)
    labels, n = ndimage.label(floor)
    on = np.zeros(n + 1, bool)
    rr = np.clip(np.round(r).astype(int), 0, z.shape[0] - 1)
    cc = np.clip(np.round(c).astype(int), 0, z.shape[1] - 1)
    on[labels[rr, cc]] = True
    on[0] = False
    floor = on[labels]
    shapes = [shapely.geometry.shape(g) for g, v in features.shapes(floor.astype(np.uint8), mask=floor, transform=tr) if v == 1]
    return shapely.make_valid(shapely.union_all(shapes)).simplify(2.0), hand


def corridor_centres(thalwegs: list[dict], floor: shapely.Geometry) -> tuple[np.ndarray, np.ndarray]:
    """Rows of centres every DX along each thalweg at offsets DX/2, 3 DX/2, ... either side, outward from the stream
    while inside the floor, so the thalweg lies on the face between the two innermost rows and no row is an island."""
    out, stream = [], []
    offsets = DX * (np.arange(int(REACH / DX)) + 0.5)
    # every thalweg sample with its stream, so a centre belongs to the stream it is nearest to and the rows of two
    # streams running close never interleave
    samples = [shapely.get_coordinates(shapely.line_interpolate_point(t["geometry"], np.arange(0.0, t["geometry"].length, 5.0))) for t in thalwegs]
    owner = cKDTree(np.vstack(samples))
    owner_stream = np.concatenate([np.full(s.shape[0], k) for k, s in enumerate(samples)])
    for k, t in enumerate(thalwegs):
        line = t["geometry"]
        if t["area_km2"] < MIN_KM2 or line.length < 2 * DX:
            continue
        s = np.arange(DX / 2, line.length, DX)
        cen = shapely.get_coordinates(shapely.line_interpolate_point(line, s))
        ahead = shapely.get_coordinates(shapely.line_interpolate_point(line, np.minimum(s + 15.0, line.length)))
        behind = shapely.get_coordinates(shapely.line_interpolate_point(line, np.maximum(s - 15.0, 0.0)))
        tang = ahead - behind
        tang /= np.maximum(np.hypot(tang[:, 0], tang[:, 1]), 1e-9)[:, None]
        normal = np.column_stack((-tang[:, 1], tang[:, 0]))
        for sign in (1.0, -1.0):
            cand = cen[:, None, :] + sign * offsets[None, :, None] * normal[:, None, :]  # (stations, offsets, 2)
            inside = shapely.contains_xy(floor, cand[..., 0], cand[..., 1])
            inside[:, 0] = True  # the innermost row always exists: the stream has a cell either side
            _d, near = owner.query(cand.reshape(-1, 2))
            inside &= (owner_stream[near] == k).reshape(inside.shape)  # this stream's ground, not a neighbour's
            reach = np.cumprod(inside, axis=1).astype(bool)  # outward until the first point off the floor
            out.append(cand[reach])
            stream.extend([k] * int(reach.sum()))
    pts = np.vstack(out) if out else np.zeros((0, 2))
    stream = np.array(stream)
    if pts.shape[0] > 1:  # two centres closer than half a cell (a confluence, a stream end) would make a sliver
        tree = cKDTree(pts)
        keep = np.ones(pts.shape[0], bool)
        for a, b in tree.query_pairs(0.5 * DX):
            if keep[a] and keep[b]:
                keep[max(a, b)] = False
        pts, stream = pts[keep], stream[keep]
    return pts, stream


def lattice_centres(box: tuple[float, float, float, float], squares: list[dict]) -> np.ndarray:
    """The 30 m lattice's cell centres over the box, aligned to the squares the engine built."""
    x0, y0, x1, y1 = box
    corner = min((shapely.get_coordinates(s["geometry"]).min(axis=0).tolist() for s in squares), default=[x0, y0])
    ox, oy = corner[0] % DX, corner[1] % DX
    xs = np.arange(np.floor((x0 - ox) / DX) * DX + ox + DX / 2, x1 + DX, DX)
    ys = np.arange(np.floor((y0 - oy) / DX) * DX + oy + DX / 2, y1 + DX, DX)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.column_stack((gx.ravel(), gy.ravel()))
    keep = (pts[:, 0] > x0 - DX) & (pts[:, 0] < x1 + DX) & (pts[:, 1] > y0 - DX) & (pts[:, 1] < y1 + DX)
    return pts[keep]


def voronoi_cells(pts: np.ndarray, box: tuple[float, float, float, float]) -> tuple[list[shapely.Polygon], np.ndarray]:
    """One clipped Voronoi polygon per point (empty where the point lies outside the box), and the number of faces of
    each: the ridges it shares with another point whose clipped cell still touches it."""
    x0, y0, x1, y1 = box
    far = 5000.0
    frame = np.array([[x0 - far, y0 - far], [x1 + far, y0 - far], [x1 + far, y1 + far], [x0 - far, y1 + far],
                      [0.5 * (x0 + x1), y0 - far], [0.5 * (x0 + x1), y1 + far], [x0 - far, 0.5 * (y0 + y1)], [x1 + far, 0.5 * (y0 + y1)]])
    vor = Voronoi(np.vstack((pts, frame)))
    clip = shapely.box(x0, y0, x1, y1)
    cells = []
    for i in range(pts.shape[0]):
        region = vor.regions[vor.point_region[i]]
        if not region or -1 in region:
            cells.append(shapely.Polygon())
            continue
        poly = shapely.Polygon(vor.vertices[region]).intersection(clip)
        cells.append(poly if poly.geom_type == "Polygon" else shapely.Polygon())
    faces = np.zeros(pts.shape[0], np.int64)
    n = pts.shape[0]
    for a, b in vor.ridge_points:
        if a < n and b < n and not cells[a].is_empty and not cells[b].is_empty:
            faces[a] += 1
            faces[b] += 1
    return cells, faces


def main(out: Path, box: tuple[float, float, float, float] = BOX, detail: tuple[float, float, float, float] = DETAIL, tag: str = "") -> None:
    pad = 400.0
    x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
    with rasterio.open(DEM) as src:
        win = from_bounds(x0, y0, x1, y1, src.transform)
        z = src.read(1, window=win).astype(np.float64)
        tr = src.window_transform(win)
        if src.nodata is not None:
            z[z == src.nodata] = np.nan
    wide = shapely.box(x0, y0, x1, y1)
    thalwegs = read("thalwegs", wide)
    squares = read("cells_30", shapely.box(*box))
    floor, _hand = floor_polygon(np.nan_to_num(z, nan=np.nanmean(z)), tr, thalwegs)
    corr, stream = corridor_centres(thalwegs, floor)
    lat = lattice_centres(box, squares)
    if corr.size:
        d, _ = cKDTree(corr).query(lat)
        lat = lat[d > NEAR]
    kind = np.concatenate((np.zeros(corr.shape[0], np.int64), np.ones(lat.shape[0], np.int64)))  # 0 corridor, 1 lattice
    pts = np.vstack((corr, lat))
    inside = (pts[:, 0] > box[0] + DX) & (pts[:, 0] < box[2] - DX) & (pts[:, 1] > box[1] + DX) & (pts[:, 1] < box[3] - DX)  # clear of the clipped edge cells
    report = {"corridor_centres": int((kind == 0).sum()), "lattice_centres": int((kind == 1).sum())}

    cells, faces = voronoi_cells(pts, box)
    area = np.array([c.area for c in cells])
    report["small_before"] = int(((area > 0) & (area < SMALL) & inside).sum())
    report["over_8_faces_before"] = int(((faces > MAX_FACES) & inside).sum())
    # merge small cells by dropping their centres (the lattice centre of a pair first, else the corridor one)
    for _round in range(MERGE_ROUNDS):
        small = np.nonzero((area > 0) & (area < SMALL) & inside)[0]
        if small.size == 0:
            break
        keep = np.ones(pts.shape[0], bool)
        keep[small] = False
        pts, kind, inside = pts[keep], kind[keep], inside[keep]
        cells, faces = voronoi_cells(pts, box)
        area = np.array([c.area for c in cells])
    # relax the lattice centres of the transition band towards their cell's centroid
    band = np.zeros(pts.shape[0], bool)
    if (kind == 0).any():
        d, _ = cKDTree(pts[kind == 0]).query(pts)
        band = (kind == 1) & (d < BAND + DX) & (faces != 4)
    for _round in range(RELAX_ROUNDS):
        for i in np.nonzero(band)[0]:
            if not cells[i].is_empty:
                pts[i] = shapely.get_coordinates(cells[i].centroid)[0]
        cells, faces = voronoi_cells(pts, box)
        area = np.array([c.area for c in cells])
    report["small_after"] = int(((area > 0) & (area < SMALL) & inside).sum())
    report["over_8_faces_after"] = int(((faces > MAX_FACES) & inside).sum())
    report["relaxed_lattice_centres"] = int(band.sum())
    have = inside & (area > 0)
    report["cells"] = int(have.sum())
    report["cells_corridor"] = int((have & (kind == 0)).sum())
    report["cells_square"] = int((have & (kind == 1) & (faces == 4)).sum())
    report["cells_transition"] = int((have & (kind == 1) & (faces != 4)).sum())
    report["faces_histogram"] = {int(f): int(((faces == f) & have).sum()) for f in np.unique(faces[have])}
    report["area_m2_min_median"] = (round(float(area[have].min()), 0), round(float(np.median(area[have])), 0))
    report["floor_km2"] = round(floor.intersection(shapely.box(*box)).area * 1e-6, 3)
    for k, v in report.items():
        print(f"{k}: {v}")

    # figure: the window and a detail
    px = tr.a
    shade = hillshade(np.nan_to_num(z, nan=np.nanmean(z)), px)
    extent = (tr.c, tr.c + z.shape[1] * px, tr.f - z.shape[0] * px, tr.f)
    colour = np.where(kind == 0, "#2a7fd4", np.where(faces == 4, "none", np.where(faces <= 5, "#ffd27f", np.where(faces <= 6, "#ffa726", np.where(faces <= MAX_FACES, "#e65100", "#d40000")))))
    polys = [shapely.get_coordinates(c.exterior) for c, ok in zip(cells, have, strict=True) if ok]
    cols = [c for c, ok in zip(colour, have, strict=True) if ok]
    edge = ["#1b4f8a" if k == 0 else "#707070" for k, ok in zip(kind, have, strict=True) if ok]
    fig, axes = plt.subplots(1, 2, figsize=(22, 10), dpi=110, gridspec_kw={"width_ratios": [1.3, 1.0]})
    for ax, view in zip(axes, (box, detail), strict=True):
        ax.imshow(shade, extent=extent, cmap="gray", vmin=0, vmax=1, alpha=0.85)
        ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors=edge, linewidths=0.35 if view is box else 0.8, alpha=0.55))
        ax.add_collection(LineCollection([shapely.get_coordinates(g) for g in getattr(floor.boundary, "geoms", [floor.boundary])], colors="#008000", linewidths=1.2))
        ax.add_collection(LineCollection([shapely.get_coordinates(t["geometry"]) for t in thalwegs], colors="#d40000", linewidths=0.9, linestyles="--"))
        if view is detail:
            ax.scatter(pts[have, 0], pts[have, 1], s=4, c="k")
        ax.set_xlim(view[0], view[2])
        ax.set_ylim(view[1], view[3])
        ax.set_aspect("equal")
    axes[0].add_patch(plt.Rectangle((detail[0], detail[1]), detail[2] - detail[0], detail[3] - detail[1], fill=False, edgecolor="#ff8800", linewidth=1.5))
    axes[0].set_title(
        f"Centres and their Voronoi cells: {report['cells_corridor']:,} corridor cells (blue) on the HAND < {HAND_FLOOR:g} m floor (green), "
        f"{report['cells_square']:,} squares, {report['cells_transition']:,} transition polygons (yellow 5, orange 6, dark 7 to 8, red over 8 faces)\n"
        f"small cells merged by dropping centres: {report['small_before']} to {report['small_after']}; over 8 faces: {report['over_8_faces_before']} to {report['over_8_faces_after']}; "
        f"faces {report['faces_histogram']}",
        fontsize=10,
    )
    axes[1].set_title("Detail: the centres (dots), the thalweg on a face between the two inner rows, no triangle in the transition", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / f"zoom_voronoi_sketch{tag}.png")
    print("wrote", out / f"zoom_voronoi_sketch{tag}.png")


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else WORK
    main(out_dir)
