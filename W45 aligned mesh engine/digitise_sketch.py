"""His sketched banks (purple strokes on screenshots of the bed-type maps) as lines on the ground: the calibration
target for the bank detector.

The screenshot shows the map's axes filled by the hillshade; the grey area's bounding box is the axes, which drew the
window box ``bed_types`` chose for that bed, so pixels map to coordinates by a linear fit. Purple pixels are taken to
the side of the thalweg they lie on, binned by station along it, and the median offset per station is the drawn bank.

    .venv\\Scripts\\python "W45 aligned mesh engine\\digitise_sketch.py" <out folder>
"""

from __future__ import annotations

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from bed_types import SITES, hillshade  # noqa: E402
from wadi2d.strips.banks import read_layers  # noqa: E402

SKETCHES = {"narrow": (7.9, 260.0), "medium": (7.2, 320.0), "wide": (20.0, 420.0)}
"""Label: the thalweg's drainage area and the half window ``bed_types`` drew it with."""
STATION = 10.0


def thalweg_part(thalwegs: dict, area: float) -> shapely.LineString:
    line = next(l for a, l in thalwegs.items() if abs(a - area) < 0.05)
    mid = line.interpolate(0.5, normalized=True)
    window = shapely.box(mid.x - 220.0, mid.y - 220.0, mid.x + 220.0, mid.y + 220.0)
    part = line.intersection(window)
    return max(part.geoms, key=lambda g: g.length) if hasattr(part, "geoms") else part


def _longest_run(ok: np.ndarray) -> tuple[int, int]:
    """First and last index of the longest run of True."""
    best, start = (0, -1), None
    for k, v in enumerate(np.append(ok, False)):
        if v and start is None:
            start = k
        elif not v and start is not None:
            if k - start > best[0]:
                best = (k - start, start)
            start = None
    return best[1], best[1] + best[0] - 1


def _edges(share: np.ndarray, window: int = 31, body: float = 0.4, edge: float = 0.3) -> tuple[int, int]:
    """First and last index of the map along one axis: the longest run of the smoothed grey share over ``body``
    (a title's text row is a few rows, a bright slope a few rows inside the map), its ends moved out to the last
    index whose own share passes ``edge``."""
    from scipy.ndimage import uniform_filter1d

    a, b = _longest_run(uniform_filter1d(share, window, mode="nearest") > body)
    lo = max(0, a - window)
    hi = min(share.size, b + window + 1)
    raw = np.nonzero(share[lo:hi] > edge)[0] + lo
    return int(raw[0]), int(raw[-1])


def _spines(dark_share: np.ndarray, a: int, b: int, reach: int = 40, share: float = 0.6) -> tuple[int, int]:
    """The axes spines nearest the grey body's ends: a row or column that is mostly dark across the whole map, which
    no text row and no hillshade shadow is. Without one within ``reach`` the body's own end stands."""
    spines = np.nonzero(dark_share > share)[0]
    above = spines[(spines <= a + reach) & (spines >= a - reach)]
    below = spines[(spines >= b - reach) & (spines <= b + reach)]
    return int(above.max()) if above.size else a, int(below.min()) if below.size else b


def axes_frame(im: np.ndarray) -> tuple[int, int, int, int]:
    """(left, right, top, bottom) pixel bounds of the hillshade: the axes box.

    The map is the longest run of rows that are mostly grey: the first version took the first such row, which on his
    screenshots was the title's own text, and so pulled every stroke south by up to 140 m (his remark of 2026-11-07).
    The box is square in metres and drawn with equal aspect, so its width in pixels is its height; that gives the edge
    the screen cut off (the fan's right edge), and a frame whose visible edges disagree with that by over 2 % fails.
    """
    r, g, b = (im[..., k].astype(int) for k in range(3))
    hi, lo = np.maximum(np.maximum(r, g), b), np.minimum(np.minimum(r, g), b)
    grey = (hi < 235) & (lo > 40) & (hi - lo < 40)
    dark = hi < 130
    top, bottom = _edges(grey.sum(axis=1) / grey.shape[1])
    top, bottom = _spines(dark.sum(axis=1) / grey.shape[1], top, bottom)
    left, right = _edges(grey[top : bottom + 1].sum(axis=0) / (bottom - top + 1))
    left, right = _spines(dark[top : bottom + 1].sum(axis=0) / (bottom - top + 1), left, right)
    side = bottom - top
    width = im.shape[1]
    cut_left, cut_right = left <= 1, right >= width - 2
    if cut_left and cut_right:
        raise ValueError("both side edges of the map are cut by the screen: the frame cannot be placed")
    if cut_right:
        right = left + side
    elif cut_left:
        left = right - side
    elif abs((right - left) - side) > 0.02 * side:
        raise ValueError(f"the map frame is not square: {right - left} by {side} px")
    return left, right, top, bottom


def purple(im: np.ndarray) -> np.ndarray:
    r, g, b = (im[..., k].astype(int) for k in range(3))
    return (b > 150) & (r > 90) & (g < 140) & (b - g > 60) & (r - g > 20)


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    gpkg, dem_path = SITES["bidah"]
    _banks, thalwegs = read_layers(gpkg)
    results = {}
    fig, axes = plt.subplots(1, 3, figsize=(18, 6.4), dpi=130)
    with rasterio.open(dem_path) as dem:
        for ax, (label, (area, half)) in zip(axes, SKETCHES.items(), strict=True):
            part = thalweg_part(thalwegs, area)
            c = part.centroid
            box = (c.x - half, c.y - half, c.x + half, c.y + half)
            im = np.asarray(Image.open(out / "sketches" / f"bidah_{label}_sketch.jpg").convert("RGB"))
            left, right, top, bottom = axes_frame(im)
            ys, xs = np.nonzero(purple(im))
            inside = (xs >= left) & (xs <= right) & (ys >= top) & (ys <= bottom)
            xs, ys = xs[inside], ys[inside]
            X = box[0] + (xs - left) / (right - left) * (box[2] - box[0])
            Y = box[3] - (ys - top) / (bottom - top) * (box[3] - box[1])
            pts = shapely.points(np.column_stack((X, Y)))
            s = np.asarray(shapely.line_locate_point(part, pts))
            near = np.asarray(shapely.get_coordinates(shapely.line_interpolate_point(part, s)))
            ahead = np.asarray(shapely.get_coordinates(shapely.line_interpolate_point(part, np.minimum(s + 5.0, part.length))))
            t = ahead - near
            t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
            dxy = np.column_stack((X, Y)) - near
            cross = t[:, 0] * dxy[:, 1] - t[:, 1] * dxy[:, 0]  # positive left of travel
            offset = np.abs(cross)
            on_line = (s > 1.0) & (s < part.length - 1.0) & (offset < 400.0)
            stations = np.arange(STATION, part.length - STATION, STATION)
            drawn = {"s": stations.tolist()}
            for side, sign in (("left", 1.0), ("right", -1.0)):
                pick = on_line & (np.sign(cross) == sign)
                values = np.full(stations.size, np.nan)
                for k, st in enumerate(stations):
                    hit = pick & (np.abs(s - st) <= 6.0)
                    if hit.sum() >= 3:
                        values[k] = float(np.median(offset[hit]))
                drawn[side] = values.tolist()
            results[label] = {"area_km2": area, "box": box, "frame_px": [left, right, top, bottom], **drawn}
            # the independent check: the thalweg, known on the ground, drawn back onto his screenshot by the same
            # frame must fall on the blue dashed line he drew his strokes against
            check, cax = plt.subplots(figsize=(7, 7), dpi=110)
            cax.imshow(im)
            tp = np.asarray(part.coords)[:, :2]
            px = left + (tp[:, 0] - box[0]) / (box[2] - box[0]) * (right - left)
            py = top + (box[3] - tp[:, 1]) / (box[3] - box[1]) * (bottom - top)
            cax.plot(px, py, color="#00c853", lw=1.4)
            cax.plot([left, right, right, left, left], [top, top, bottom, bottom, top], color="#00c853", lw=0.8, ls=":")
            cax.set_title(f"{label}: his screenshot with the thalweg mapped back by the fitted frame (green); it must lie on his blue dashes", fontsize=7)
            cax.axis("off")
            check.savefig(out / f"sketch_check_{label}.png", bbox_inches="tight")
            plt.close(check)
            # the check: the digitised lines on the hillshade
            shade, _z = hillshade(dem, box)
            ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1)
            tp = np.asarray(part.coords)[:, :2]
            ax.plot(tp[:, 0], tp[:, 1], "--", color="#1f77b4", lw=1)
            ax.scatter(X[::20], Y[::20], s=1, color="#b070ff", alpha=0.5)
            for side, sign in (("left", 1.0), ("right", -1.0)):
                vals = np.array(drawn[side])
                ok = ~np.isnan(vals)
                if ok.any():
                    p = np.array([part.interpolate(v).coords[0] for v in stations[ok]])[:, :2]
                    a = np.array([part.interpolate(min(v + 5.0, part.length)).coords[0] for v in stations[ok]])[:, :2]
                    tt = a - p
                    tt /= np.maximum(np.hypot(tt[:, 0], tt[:, 1]), 1e-9)[:, None]
                    nn = np.column_stack((-tt[:, 1], tt[:, 0])) * sign
                    line = p + nn * vals[ok][:, None]
                    ax.plot(line[:, 0], line[:, 1], color="#7a00cc", lw=1.8)
            widths = np.array(drawn["left"]) + np.array(drawn["right"])
            ax.set_title(f"{label}: his banks digitised, width median {np.nanmedian(widths):.0f} m ({np.nanmin(widths):.0f} to {np.nanmax(widths):.0f}), {int((~np.isnan(widths)).sum())} of {stations.size} stations", fontsize=8)
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
            ax.set_aspect("equal")
            ax.tick_params(labelsize=6)
            ax.ticklabel_format(useOffset=False, style="plain")
    (out / "sketched_banks.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    fig.suptitle("His sketched banks mapped to the ground (purple dots the strokes, purple lines the station medians); blue: thalweg", fontsize=9)
    fig.savefig(out / "sketched_banks.png", bbox_inches="tight")
    for label, r in results.items():
        w = np.array(r["left"]) + np.array(r["right"])
        print(label, "frame px", r["frame_px"], "width median", round(float(np.nanmedian(w))), "left median", round(float(np.nanmedian(r["left"]))), "right median", round(float(np.nanmedian(r["right"]))))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
