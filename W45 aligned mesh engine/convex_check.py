"""His idea of 2026-11-07, late: banks are convex lines along the wadis. Does a convex break of slope place the bank
better than a slope limit or a rise over the bed?

Going out from the thalweg across a wadi the ground is flat on the floor, climbs the bank, and flattens again on the
terrace: the toe is a concave break (the slope grows), the top of the bank a convex one (the slope falls). The
detector here takes, per section, the first strong convex break (the fall of slope over a run) that stands a height
over the bed; it is scored on the three Bidah windows against his strokes and the 100-yr flood margins, beside the
slope-limit and rise detectors of the earlier sweep.

    .venv\\Scripts\\python "W45 aligned mesh engine\\convex_check.py" <out folder with bed_types/>
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
import bank_sweep as bs  # noqa: E402
from bed_types import hillshade  # noqa: E402
from wadi2d.strips.banks import read_layers  # noqa: E402

RUNS = (10.0, 20.0, 40.0)
KAPPAS = (0.005, 0.01, 0.02, 0.04)
"""Fall of slope over the run, per metre: 0.01 is a 10 % slope flattening to 0 over 10 m."""
HEIGHTS = (1.0, 2.0)


def convex_points(prof: np.ndarray, run: float, kappa: float, h: float) -> np.ndarray:
    """(sections, sides) offset of the first strong convex break standing ``h`` over the bed; SECTION_HALF where none."""
    n_st, _two, m = prof.shape
    out = np.full((n_st, 2), bs.SECTION_HALF)
    r = int(run)
    bed = np.nanmin(prof[:, :, :16], axis=2)
    for k in range(n_st):
        b = min(bed[k, 0], bed[k, 1])
        for side in range(2):
            z = prof[k, side]
            if m < 2 * r + 3:
                continue
            slope = np.full(m, np.nan)
            slope[r // 2 : m - (r - r // 2)] = (z[r:] - z[:-r]) / r  # centred slope over the run
            curv = np.full(m, np.nan)
            curv[r // 2 : m - (r - r // 2)] = (slope[r:] - slope[:-r]) / r  # fall of slope over the next run
            convex = (curv < -kappa) & ((z - b) >= h)
            convex[:3] = False
            where = np.nonzero(convex)[0]
            if where.size == 0:
                continue
            # the first convex stretch: take its strongest point
            start = where[0]
            end = start
            while end + 1 < m and convex[end + 1]:
                end += 1
            d = start + int(np.nanargmin(curv[start : end + 1]))
            out[k, side] = float(d)
    for side in range(2):  # the same running median the other detectors get
        a = out[:, side].copy()
        for k in range(n_st):
            out[k, side] = np.median(a[max(0, k - 2) : k + 3])
    return out


def main(out: Path) -> None:
    gpkg, dem_path = bs.SITES["bidah"]
    _banks, thalwegs = read_layers(gpkg)
    windows = {}
    with rasterio.open(dem_path) as dem, rasterio.open(bs.DEPTH_MAP) as dm:
        for label, (area, half) in bs.SKETCHES.items():
            part = bs.thalweg_part(thalwegs, area)
            c = part.centroid
            box = (c.x - half, c.y - half, c.x + half, c.y + half)
            s, pts, normal = bs.sections(part)
            offsets, prof = bs.profiles(bs.Ground(dem, box), pts, normal)
            _o, depth = bs.profiles(bs.Ground(dm, box), pts, normal)
            if dm.nodata is not None:
                depth = np.where(depth == dm.nodata, 0.0, depth)
            windows[label] = dict(part=part, box=box, pts=pts, normal=normal, offsets=offsets, prof=prof, depth=depth,
                                  trees=bs.strokes(out / "bed_types", label, box, part),
                                  f05=bs.detect("flood", prof, offsets, depth, d=0.5), f02=bs.detect("flood", prof, offsets, depth, d=0.2))

        def score_all(name, maker):
            row = {"name": name}
            for label, w in windows.items():
                found = maker(w)
                med, _share, width = bs.score(found, w["pts"], w["normal"], w["trees"])
                both5 = (found < bs.SECTION_HALF) & (w["f05"] < bs.SECTION_HALF)
                both2 = (found < bs.SECTION_HALF) & (w["f02"] < bs.SECTION_HALF)
                row[label] = dict(
                    width=width, strokes=med,
                    off05=float(np.median(np.abs(found - w["f05"])[both5])) if both5.any() else float("nan"),
                    off02=float(np.median(np.abs(found - w["f02"])[both2])) if both2.any() else float("nan"),
                    sides=int((found < bs.SECTION_HALF).sum()), of=2 * found.shape[0],
                )
            return row

        rows = []
        for run, kappa, h in itertools.product(RUNS, KAPPAS, HEIGHTS):
            rows.append(score_all(f"convex run {run:.0f} m, slope fall {kappa:g}/m, {h:g} m up", lambda w, run=run, kappa=kappa, h=h: convex_points(w["prof"], run, kappa, h)))
        rows.append(score_all("slope 5 % over 40 m, 2 m up (his rule)", lambda w: bs.detect("slope", w["prof"], w["offsets"], w["depth"], s=0.05, run=40, h=2.0)))
        rows.append(score_all("rise 2 m over the bed (the engine's default)", lambda w: bs.detect("rise", w["prof"], w["offsets"], w["depth"], h=2.0)))
        print("detector | narrow: width, off his strokes, off the 0.5 m margin, sides found | medium | wide")
        for r in rows:
            cells = []
            for label in ("narrow", "medium", "wide"):
                d = r[label]
                cells.append(f"{d['width']:5.0f} m {d['strokes']:4.1f} {d['off05']:4.1f} {d['sides']:3d}/{d['of']}")
            print(f"{r['name']:46s} | " + " | ".join(cells))
        # the figure: the best convex setting by the strokes on the two wadis, beside his rule
        best = min(rows[:-2], key=lambda r: r["narrow"]["strokes"] + r["medium"]["strokes"])
        print("best convex by his strokes:", best["name"])
        fig, axes = plt.subplots(1, 3, figsize=(19, 6.6), dpi=120)
        parts = best["name"].split()
        run, kappa, h = float(parts[2]), float(parts[6].rstrip("/m,")), float(parts[7])
        for ax, (label, w) in zip(axes, windows.items(), strict=True):
            box = w["box"]
            shade, _z = hillshade(dem, box)
            ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1)
            for tree in w["trees"]:
                ax.scatter(tree.data[::12, 0], tree.data[::12, 1], s=1.5, color="#b070ff", alpha=0.5)
            for found, colour, lw, name in ((convex_points(w["prof"], run, kappa, h), "#c00000", 1.8, "convex break"),
                                            (bs.detect("slope", w["prof"], w["offsets"], w["depth"], s=0.05, run=40, h=2.0), "#008000", 1.1, "slope 5 %"),
                                            (w["f05"], "#004c99", 1.0, "flood 0.5 m")):
                for side, sign in enumerate((1.0, -1.0)):
                    on = found[:, side] < bs.SECTION_HALF
                    bank = w["pts"][on] + sign * w["normal"][on] * found[on, side][:, None]
                    ax.plot(bank[:, 0], bank[:, 1], color=colour, lw=lw, label=name if side == 0 else None)
            tp = np.asarray(w["part"].coords)[:, :2]
            ax.plot(tp[:, 0], tp[:, 1], "--", color="#1f77b4", lw=0.9)
            d = best[label]
            ax.set_title(f"{label}: convex width {d['width']:.0f} m, {d['strokes']:.1f} m off his strokes, {d['off05']:.1f} m off the 0.5 m margin", fontsize=8.5)
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
            ax.set_aspect("equal")
            ax.tick_params(labelsize=6)
            ax.ticklabel_format(useOffset=False, style="plain")
        axes[0].legend(fontsize=7, loc="lower right")
        fig.suptitle(f"Banks as convex breaks of slope ({best['name']}, red) against his 5 % slope rule (green), the 0.5 m flood margin (dark blue) and his strokes (purple)", fontsize=9)
        fig.savefig(out / "bed_types" / "convex_check.png", bbox_inches="tight")
        print("wrote", out / "bed_types" / "convex_check.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
