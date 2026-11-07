"""Maps of the aligned mesh on Block 2's bed types, under today's rule and two adaptive candidates, for his choice.

Sites come from W26's suggested thalwegs on Bidah and Faydh. The suggested bank lines stand one cell either side of
the thalweg by construction (W26's rule), so the bed's true width is measured here from the DEM: at stations along
the thalweg a section across it, and the bank where the ground first rises ``BANK_RISE`` above the thalweg's bed.

Rules drawn:
  A  today: six rows of 10 m, the snapped rows one cell either side of the thalweg (the suggested banks)
  B  adaptive, inner rows about 10 m apart: the snapped rows on the measured banks, rows between them 10 m apart or
     one row, two outer rows 10 and 20 m beyond each bank
  C  adaptive, inner rows about 20 m apart, outer rows 20 and 40 m beyond

    .venv\\Scripts\\python "W45 aligned mesh engine\\bed_types.py" <out folder>
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wadi2d.grid.tiles import TileGrid  # noqa: E402
from wadi2d.strips.banks import pair_banks, read_layers  # noqa: E402
from wadi2d.strips.mesher import Corridor, build_strip_mesh, fold_free_pieces  # noqa: E402

SITES = {
    "bidah": (ROOT / "W26 suggested breaklines/suggested/bidah/suggested_breaklines.gpkg", Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Terrain\GGC_2_MERGE_HDSM_5.tif")),
    "faydh": (ROOT / "W26 suggested breaklines/suggested/faydh/suggested_breaklines.gpkg", ROOT / "W11 validation round two/t2_faydh/terrain/faydh_0p5m.tif"),
}
DX = 20.0
BANK_RISE = 1.5
"""The bank: where a section first stands this far above the thalweg's bed, m (a bankfull proxy for Batinah wadis)."""
SECTION_HALF = 200.0
STATION = 10.0


def sample(dem, xs, ys) -> np.ndarray:
    return np.array([v[0] for v in dem.sample(np.column_stack((xs, ys)))], np.float64)


def measured_banks(dem, thalweg: shapely.LineString) -> tuple[shapely.LineString, shapely.LineString, np.ndarray, np.ndarray]:
    """Left and right bank lines from DEM sections across the thalweg, and the half-widths per station."""
    s = np.arange(STATION, thalweg.length - STATION, STATION)
    pts = np.array([thalweg.interpolate(v).coords[0] for v in s])[:, :2]
    ahead = np.array([thalweg.interpolate(min(v + STATION, thalweg.length)).coords[0] for v in s])[:, :2]
    t = ahead - pts
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
    normal = np.column_stack((-t[:, 1], t[:, 0]))  # left of travel
    offsets = np.arange(-SECTION_HALF, SECTION_HALF + 0.5, 1.0)
    left, right = np.zeros(s.size), np.zeros(s.size)
    for k, (p, n) in enumerate(zip(pts, normal, strict=True)):
        xs, ys = p[0] + offsets * n[0], p[1] + offsets * n[1]
        z = sample(dem, xs, ys)
        middle = offsets.size // 2
        bed = np.nanmin(z[middle - 15 : middle + 16])  # the lowest ground within 15 m of the thalweg
        above = z > bed + BANK_RISE
        li = np.nonzero(above[: middle + 1][::-1])[0]
        ri = np.nonzero(above[middle:])[0]
        left[k] = float(li[0]) if li.size else SECTION_HALF
        right[k] = float(ri[0]) if ri.size else SECTION_HALF
    # a running median keeps a section's odd pixel from kinking the line
    def smooth(a):
        out = a.copy()
        for k in range(a.size):
            out[k] = np.median(a[max(0, k - 2) : k + 3])
        return out

    left, right = smooth(left), smooth(right)
    lb = shapely.LineString(pts + normal * left[:, None])
    rb = shapely.LineString(pts - normal * right[:, None])
    return lb, rb, left, right


def rule_offsets(rule: str, half_left: float, half_right: float) -> tuple[np.ndarray, dict]:
    """Row offsets (left negative in the corridor's own frame? no: positive to the left of travel) and which rows snap:
    the mesher's offsets are along the station normal, which points left of travel."""
    if rule == "A":
        off = np.arange(-30.0, 30.1, 10.0)
        return off, {"left": 10.0, "right": -10.0}
    spacing, outer = (10.0, (10.0, 20.0)) if rule == "B" else (20.0, (20.0, 40.0))
    width = half_left + half_right
    inner = max(int(round(width / spacing)) - 1, 1)
    between = np.linspace(-half_right, half_left, inner + 2)[1:-1]
    off = np.concatenate((
        [-half_right - outer[1], -half_right - outer[0], -half_right], between, [half_left, half_left + outer[0], half_left + outer[1]]
    ))  # fmt: skip
    return np.round(off, 2), {"left": half_left, "right": -half_right}


def corridor_for(name: str, thalweg: shapely.LineString, rule: str, banks: tuple, suggested: tuple | None) -> list[Corridor]:
    lb, rb, left, right = banks
    hl, hr = float(np.median(left)), float(np.median(right))
    off, snap_at = rule_offsets(rule, hl, hr)
    if rule == "A":
        lines = suggested if suggested is not None else (lb, rb)
    else:
        lines = (lb, rb)
    snap = {int(np.argmin(np.abs(off - snap_at["left"]))): lines[0], int(np.argmin(np.abs(off - snap_at["right"]))): lines[1]}
    c = Corridor(name, thalweg, off, DX, snap)
    pieces, whole = fold_free_pieces(c)
    if whole:
        return [c]
    return [Corridor(f"{name}_{k}", shapely.LineString(p), off, DX, snap) for k, p in enumerate(pieces) if p.shape[0] >= 4]


def grid_for(box: tuple[float, float, float, float]) -> TileGrid:
    x0, y0, x1, y1 = box
    x0, y1 = np.floor(x0 / DX) * DX, np.ceil(y1 / DX) * DX
    nx, ny = int(np.ceil((x1 - x0) / DX)), int(np.ceil((y1 - y0) / DX))
    return TileGrid.from_mask(np.ones((ny, nx), bool), x0, y1, DX)


def hillshade(dem, box):
    win = from_bounds(*box, transform=dem.transform)
    z = dem.read(1, window=win, out_shape=(600, 600), resampling=rasterio.enums.Resampling.bilinear).astype(np.float64)
    z = np.where(z == dem.nodata, np.nan, z) if dem.nodata is not None else z
    gy, gx = np.gradient(z, (box[3] - box[1]) / z.shape[0], (box[2] - box[0]) / z.shape[1])
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(315.0), np.radians(45.0)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(shade, 0.0, 1.0), z


def draw(ax, dem, box, mesh, thalweg, banks, suggested, title: str) -> None:
    shade, z = hillshade(dem, box)
    ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0.0, vmax=1.0, zorder=0)
    ax.contour(np.linspace(box[0], box[2], z.shape[1]), np.linspace(box[3], box[1], z.shape[0]), z, levels=12, colors="#6b4e00", linewidths=0.3, alpha=0.6, zorder=1)
    xs = np.arange(np.floor(box[0] / DX) * DX, box[2] + DX, DX)
    ys = np.arange(np.floor(box[1] / DX) * DX, box[3] + DX, DX)
    ax.vlines(xs, box[1], box[3], colors="0.85", lw=0.3, zorder=2)
    ax.hlines(ys, box[0], box[2], colors="0.85", lw=0.3, zorder=2)
    if mesh is not None:
        geo = mesh.geometry
        polys = [np.column_stack((geo.x[geo.ring_node[a:b]], geo.y[geo.ring_node[a:b]])) for a, b in zip(geo.ring_start[:-1], geo.ring_start[1:], strict=True)]
        kinds = mesh.corridor
        corridor_polys = [p for p, k in zip(polys, kinds, strict=True) if k >= 0]
        gap_polys = [p for p, k in zip(polys, kinds, strict=True) if k < 0]
        ax.add_collection(PolyCollection(corridor_polys, facecolors=(0.2, 0.5, 0.9, 0.25), edgecolors="#1f3b73", linewidths=0.5, zorder=3))
        ax.add_collection(PolyCollection(gap_polys, facecolors=(1.0, 0.6, 0.1, 0.18), edgecolors="#b35a00", linewidths=0.4, zorder=3))
    lb, rb, _l, _r = banks
    ax.add_collection(LineCollection([np.asarray(lb.coords)[:, :2], np.asarray(rb.coords)[:, :2]], colors="#c00000", linewidths=1.3, zorder=5))
    if suggested is not None:
        ax.add_collection(LineCollection([np.asarray(s.coords)[:, :2] for s in suggested], colors="#ff9ec4", linewidths=0.9, linestyles=(0, (3, 2)), zorder=4))
    t = np.asarray(thalweg.coords)[:, :2]
    ax.plot(t[:, 0], t[:, 1], color="#1f77b4", lw=1.0, ls="--", zorder=5)
    ax.set_xlim(box[0], box[2])
    ax.set_ylim(box[1], box[3])
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=9)
    ax.tick_params(labelsize=6)
    ax.ticklabel_format(useOffset=False, style="plain")


def mesh_stats(mesh) -> str:
    geo = mesh.geometry
    _a, cx, cy = geo.areas_centroids()
    _len, nfx, nfy, _xf, _yf = geo.faces(cx, cy)
    inner = geo.face_cell[:, 1] >= 0
    L, R = geo.face_cell[inner, 0], geo.face_cell[inner, 1]
    dn = (cx[R] - cx[L]) * nfx[inner] + (cy[R] - cy[L]) * nfy[inner]
    cells = int((mesh.corridor >= 0).sum())
    return f"{cells} corridor cells, {int((mesh.corridor < 0).sum())} triangles, smallest dn {max(dn.min(), 0.15 * DX):.1f} m (step {max(dn.min(), 0.15 * DX) / DX:.2f} of the squares')"


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for site, (gpkg, dem_path) in SITES.items():
        banks_raw, thalwegs = read_layers(gpkg)
        pairs = pair_banks(banks_raw, thalwegs)
        with rasterio.open(dem_path) as dem:
            measured = {}
            for area, line in thalwegs.items():
                if line.length < 400.0:
                    continue
                mid = line.interpolate(0.5, normalized=True)
                window = shapely.box(mid.x - 220.0, mid.y - 220.0, mid.x + 220.0, mid.y + 220.0)
                part = line.intersection(window)
                part = max(part.geoms, key=lambda g: g.length) if hasattr(part, "geoms") else part
                if part.geom_type != "LineString" or part.length < 200.0:
                    continue
                lb, rb, left, right = measured_banks(dem, part)
                measured[area] = (part, (lb, rb, left, right), float(np.median(left + right)))
            widths = sorted(measured.items(), key=lambda kv: kv[1][2])
            print(site, "measured bed widths (m) by thalweg:", [(round(a, 1), round(w)) for a, (_p, _b, w) in widths])
            picks = {}
            for label, lo, hi in (("narrow", 0.0, 40.0), ("medium", 40.0, 120.0), ("wide", 120.0, 1e9)):
                cands = [(a, v) for a, v in widths if lo <= v[2] < hi]
                if cands:
                    picks[label] = max(cands, key=lambda kv: kv[0])  # the biggest wadi of the class
            for label, (area, (part, banks, width)) in picks.items():
                suggested = None
                near = [p for p in pairs if abs(p.area_km2 - area) < 1e-6]
                if near:
                    suggested = (near[0].left, near[0].right)
                c = part.centroid
                half = 260.0 if width < 40 else (320.0 if width < 120 else 420.0)
                box = (c.x - half, c.y - half, c.x + half, c.y + half)
                grid = grid_for((box[0] - 100, box[1] - 100, box[2] + 100, box[3] + 100))
                fig, axes = plt.subplots(1, 3, figsize=(18, 6.6), dpi=150)
                for ax, rule in zip(axes, ("A", "B", "C"), strict=True):
                    try:
                        if rule == "A" and (suggested is None or not any(l.intersects(shapely.box(*box)) for l in suggested)):
                            raise ValueError("W26 suggested no bank on this stretch (no defined wadi), so today's rule builds no corridor here")
                        corridors = corridor_for(f"{site}_{label}", part, rule, banks, suggested)
                        if not corridors:
                            raise ValueError("the lines cover only part of this stretch or fold at its bends: no corridor survives the fold test")
                        mesh = build_strip_mesh(grid, corridors)
                        stats = mesh_stats(mesh)
                    except Exception as error:  # a rule that fails here is a finding too
                        mesh, stats = None, f"not built: {str(error)[:110]}"
                    names = {"A": "A today: 6 rows of 10 m on the suggested lines", "B": "B adaptive, rows about 10 m, banks measured", "C": "C adaptive, rows about 20 m, banks measured"}
                    draw(ax, dem, box, mesh, part, banks, suggested, f"{names[rule]}\n{stats}")
                fig.suptitle(f"{site.title()}, {label} bed: wadi of {area:.1f} km2, measured bed width {width:.0f} m (bank where the ground rises {BANK_RISE:g} m over the thalweg). Red: measured banks; pink dashed: W26's suggested lines; blue: thalweg; blue cells: corridor; orange: gap triangles; grey: 20 m squares.", fontsize=9)
                path = out / f"{site}_{label}.png"
                fig.savefig(path, bbox_inches="tight")
                plt.close(fig)
                made.append(path)
                print("wrote", path)
    print("done", len(made))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
