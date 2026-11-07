"""Bank detectors against his sketched banks, on the three Bidah windows: which rule, with which numbers, lands in his
band. His strokes are eyeballed, so the score is a distance band, not a fit: the median distance from the detected
bank to the nearest stroke pixel on that side, and the share of detected stations within 25 m of one.

Detectors, each walking a section outward from the thalweg:
  slope   the hillslope starts: ground slope over ``run`` m above ``s`` and the ground ``h`` above the bed
  rise    the ground stands ``h`` above the bed
  rough   the ground gets rough: the residual of a 20 m line fit above ``sigma`` (the valley floor is smooth)
  slope+rough  either
  flood   his idea: the water runs inside the wadi course, so the margin of the flooded area in a run on squares
          (max depth above ``d``, contiguous from the thalweg, Bidah's 100-yr run at 5 m) is the bank

    .venv\\Scripts\\python "W45 aligned mesh engine\\bank_sweep.py" <out folder>
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
from PIL import Image  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402
from scipy.ndimage import map_coordinates  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from bed_types import SITES, hillshade  # noqa: E402
from digitise_sketch import SKETCHES, axes_frame, purple, thalweg_part  # noqa: E402
from wadi2d.strips.banks import read_layers  # noqa: E402

STATION = 10.0
SECTION_HALF = 300.0
BAND_M = 25.0
DEPTH_MAP = ROOT / "W1 research and design note" / "validation" / "block2_full" / "runs" / "conv_dx5_s1" / "maps" / "max_depth.tif"


class Ground:
    """A DEM window in memory, sampled bilinearly."""

    def __init__(self, dem, box, margin: float = 400.0) -> None:
        x0, y0, x1, y1 = box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin
        win = from_bounds(x0, y0, x1, y1, transform=dem.transform)
        self.z = dem.read(1, window=win).astype(np.float64)
        t = dem.window_transform(win)
        self.x0, self.y0, self.p = t.c, t.f, t.a

    def __call__(self, xs, ys):
        cols = (np.asarray(xs) - self.x0) / self.p - 0.5
        rows = (self.y0 - np.asarray(ys)) / self.p - 0.5
        return map_coordinates(self.z, [rows, cols], order=1, mode="nearest")


def sections(thalweg: shapely.LineString):
    s = np.arange(STATION, thalweg.length - STATION, STATION)
    pts = np.array([thalweg.interpolate(v).coords[0] for v in s])[:, :2]
    ahead = np.array([thalweg.interpolate(min(v + STATION, thalweg.length)).coords[0] for v in s])[:, :2]
    t = ahead - pts
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
    normal = np.column_stack((-t[:, 1], t[:, 0]))
    return s, pts, normal


def profiles(ground: Ground, pts, normal):
    """(stations, sides, offsets) ground along each half section, offsets 0..SECTION_HALF at 1 m."""
    offsets = np.arange(0.0, SECTION_HALF + 0.5, 1.0)
    out = np.zeros((pts.shape[0], 2, offsets.size))
    for k, (p, n) in enumerate(zip(pts, normal, strict=True)):
        for side, sign in enumerate((1.0, -1.0)):
            out[k, side] = ground(p[0] + sign * offsets * n[0], p[1] + sign * offsets * n[1])
    return offsets, out


def detect(kind: str, prof: np.ndarray, offsets: np.ndarray, depth=None, **p) -> np.ndarray:
    """(stations, sides) offset of the bank, SECTION_HALF where none."""
    n_st, _two, m = prof.shape
    out = np.full((n_st, 2), SECTION_HALF)
    bed = np.nanmin(prof[:, :, :16], axis=2)
    for k in range(n_st):
        for side in range(2):
            z = prof[k, side]
            b = min(bed[k, 0], bed[k, 1])
            hit = np.zeros(m, bool)
            if kind == "flood":
                wet = depth[k, side] > p["d"]
                dry = np.nonzero(~wet)[0]
                # the first dry stretch of 10 m from the thalweg outward ends the flooded course
                end = m
                for d0 in dry:
                    if d0 >= 3 and (~wet[d0 : d0 + 10]).all():
                        end = d0
                        break
                out[k, side] = float(end) if end < m else SECTION_HALF
                continue
            if kind in ("slope", "slope+rough"):
                run = int(p["run"])
                slope = np.zeros(m)
                slope[: m - run] = (z[run:] - z[:-run]) / run
                hit |= (slope > p["s"]) & (z - b > p["h"])
            if kind == "rise":
                hit |= z - b > p["h"]
            if kind in ("rough", "slope+rough"):
                w = 10
                resid = np.zeros(m)
                for d in range(w, m - w):
                    seg = z[d - w : d + w + 1]
                    x = np.arange(seg.size)
                    a, c = np.polyfit(x, seg, 1)
                    resid[d] = np.std(seg - (a * x + c))
                hit |= (resid > p["sigma"]) & (z - b > 0.5)
            where = np.nonzero(hit[1:])[0]
            if where.size:
                out[k, side] = float(where[0] + 1)
    # a running median along the line
    for side in range(2):
        a = out[:, side].copy()
        for k in range(n_st):
            out[k, side] = np.median(a[max(0, k - 2) : k + 3])
    return out


def strokes(out: Path, label: str, box, part: shapely.LineString):
    """The sketch's purple pixels on the ground, split by side of the thalweg."""
    im = np.asarray(Image.open(out / "sketches" / f"bidah_{label}_sketch.jpg").convert("RGB"))
    left, right, top, bottom = axes_frame(im)
    ys, xs = np.nonzero(purple(im))
    inside = (xs >= left) & (xs <= right) & (ys >= top) & (ys <= bottom)
    X = box[0] + (xs[inside] - left) / (right - left) * (box[2] - box[0])
    Y = box[3] - (ys[inside] - top) / (bottom - top) * (box[3] - box[1])
    pts = shapely.points(np.column_stack((X, Y)))
    s = np.asarray(shapely.line_locate_point(part, pts))
    near = np.asarray(shapely.get_coordinates(shapely.line_interpolate_point(part, s)))
    ahead = np.asarray(shapely.get_coordinates(shapely.line_interpolate_point(part, np.minimum(s + 5.0, part.length))))
    t = ahead - near
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
    d = np.column_stack((X, Y)) - near
    cross = t[:, 0] * d[:, 1] - t[:, 1] * d[:, 0]
    return [cKDTree(np.column_stack((X, Y))[cross > 0]), cKDTree(np.column_stack((X, Y))[cross < 0])]


def score(found: np.ndarray, pts, normal, trees) -> tuple[float, float, float]:
    """Median distance to his stroke on each side, the share within the band, and the median width found."""
    dist = []
    for side, sign in enumerate((1.0, -1.0)):
        on = found[:, side] < SECTION_HALF
        if not on.any():
            continue
        bank = pts[on] + sign * normal[on] * found[on, side][:, None]
        dist.append(trees[side].query(bank)[0])
    if not dist:
        return float("inf"), 0.0, float("nan")
    dist = np.concatenate(dist)
    width = (found[:, 0] + found[:, 1])[(found < SECTION_HALF).all(axis=1)]
    return float(np.median(dist)), float((dist < BAND_M).mean()), float(np.median(width)) if width.size else float("nan")


CANDIDATES = (
    [("slope", {"s": s, "run": run, "h": h}) for s, run, h in itertools.product((0.04, 0.06, 0.08, 0.12, 0.18), (20, 40), (0.5, 1.0, 2.0, 3.0))]
    + [("rise", {"h": h}) for h in (1.5, 2.5, 3.5, 5.0, 7.0)]
    + [("rough", {"sigma": sg}) for sg in (0.1, 0.2, 0.35)]
    + [("slope+rough", {"s": s, "run": 20, "h": 1.0, "sigma": sg}) for s, sg in itertools.product((0.06, 0.12), (0.2, 0.35))]
    + [("flood", {"d": d}) for d in (0.03, 0.05, 0.1, 0.2, 0.3, 0.5)]
)


def main(out: Path) -> None:
    gpkg, dem_path = SITES["bidah"]
    _banks, thalwegs = read_layers(gpkg)
    windows = {}
    with rasterio.open(dem_path) as dem:
        for label, (area, half) in SKETCHES.items():
            part = thalweg_part(thalwegs, area)
            c = part.centroid
            box = (c.x - half, c.y - half, c.x + half, c.y + half)
            ground = Ground(dem, box)
            s, pts, normal = sections(part)
            offsets, prof = profiles(ground, pts, normal)
            with rasterio.open(DEPTH_MAP) as dm:
                wetness = Ground(dm, box)
                nodata = dm.nodata
            _offsets, depth = profiles(wetness, pts, normal)
            if nodata is not None:
                depth = np.where(depth == nodata, 0.0, depth)
            windows[label] = dict(part=part, box=box, pts=pts, normal=normal, offsets=offsets, prof=prof, depth=depth, trees=strokes(out, label, box, part))
        table = []
        for kind, params in CANDIDATES:
            row = {"kind": kind, **params}
            meds, shares = [], []
            for label, w in windows.items():
                found = detect(kind, w["prof"], w["offsets"], w["depth"], **params)
                med, share, width = score(found, w["pts"], w["normal"], w["trees"])
                row[f"{label}_median_m"], row[f"{label}_in_band"], row[f"{label}_width_m"] = round(med, 1), round(share, 2), round(width, 1) if width == width else None
                meds.append(med)
                shares.append(share)
            row["mean_median_m"], row["mean_in_band"] = round(float(np.mean(meds)), 1), round(float(np.mean(shares)), 2)
            table.append(row)
        table.sort(key=lambda r: (r["mean_median_m"], -r["mean_in_band"]))
        (out / "bank_sweep.json").write_text(json.dumps(table, indent=1), encoding="utf-8")
        print("best ten by mean median distance to his strokes (m), share within 25 m, widths narrow/medium/wide:")
        for r in table[:10]:
            params = {k: v for k, v in r.items() if k in ("s", "run", "h", "sigma", "d")}
            print(f"  {r['kind']:12s} {str(params):44s} {r['mean_median_m']:6.1f} m  {r['mean_in_band']:.2f}   {r['narrow_width_m']}, {r['medium_width_m']}, {r['wide_width_m']}")
        # the best three drawn against his strokes
        fig, axes = plt.subplots(3, 3, figsize=(18, 18), dpi=110)
        for i, r in enumerate(table[:3]):
            params = {k: v for k, v in r.items() if k in ("s", "run", "h", "sigma", "d")}
            for j, (label, w) in enumerate(windows.items()):
                ax = axes[i, j]
                box = w["box"]
                shade, _z = hillshade(dem, box)
                ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1)
                for tree in w["trees"]:
                    ax.scatter(tree.data[::15, 0], tree.data[::15, 1], s=1.2, color="#b070ff", alpha=0.6)
                found = detect(r["kind"], w["prof"], w["offsets"], w["depth"], **params)
                for side, sign in enumerate((1.0, -1.0)):
                    on = found[:, side] < SECTION_HALF
                    bank = w["pts"][on] + sign * w["normal"][on] * found[on, side][:, None]
                    ax.plot(bank[:, 0], bank[:, 1], color="#c00000", lw=1.6)
                tp = np.asarray(w["part"].coords)[:, :2]
                ax.plot(tp[:, 0], tp[:, 1], "--", color="#1f77b4", lw=0.9)
                ax.set_title(f"{r['kind']} {params}\n{label}: median {r[f'{label}_median_m']} m off his strokes, {r[f'{label}_in_band']:.0%} within 25 m, width {r[f'{label}_width_m']} m", fontsize=8)
                ax.set_xlim(box[0], box[2])
                ax.set_ylim(box[1], box[3])
                ax.set_aspect("equal")
                ax.tick_params(labelsize=6)
                ax.ticklabel_format(useOffset=False, style="plain")
        fig.suptitle("The three detectors nearest his sketched banks (purple dots), red: the bank found", fontsize=10)
        fig.savefig(out / "bank_sweep_best.png", bbox_inches="tight")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
