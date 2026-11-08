"""Where the aligned strip holds less water than the converged squares (W48, 2026-11-08).

Faydh 01's main stem, 4 to 20 km, a steady 300 m3/s, on the W47 option A kernels (`W47 .../depth_carry/steady`): the
20 m centre mesh holds 4.5 % less water in its footprint than the 2 m squares, the 10 m one 1.2 %, which tracks the
race's excess (4.6 and 1.7 % over the 5 m squares). Per strip cell: the water under the strip's own final level
against the water under the 2 m squares' final surface over the same pixels of the 0.5 m DEM. Grouped by the kind of
cell (the pair on the thalweg, the band's polygons), along the stem, and against the cell's own geometry.

    .venv\\Scripts\\python "W48 aligned cells race excess\\where_the_water_is.py" [ce20|ce10]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import fiona
import numpy as np
import shapely
from rasterio import features
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W47 face level carried to the face"))
import steady_surfaces as ss  # noqa: E402

from wadi2d.strips.banks import read_thalwegs  # noqa: E402
from wadi2d.strips.centres import chain_streams  # noqa: E402

RUNS = ROOT / "W47 face level carried to the face" / "depth_carry" / "steady"
W26 = ROOT / "W26 suggested breaklines" / "suggested" / "faydh" / "suggested_breaklines.gpkg"
OUT = Path(__file__).resolve().parent / "where_the_water_is"


def main(name: str) -> None:
    import rasterio

    OUT.mkdir(parents=True, exist_ok=True)
    cells, props = [], []
    with fiona.open(RUNS / name / "maps" / "strip_mesh.gpkg", layer="strip_cells") as src:
        for feat in src:
            cells.append(shapely.geometry.shape(feat["geometry"]))
            props.append(dict(feat["properties"]))
    faces_of = np.zeros(len(cells), int)
    with fiona.open(RUNS / name / "maps" / "strip_mesh.gpkg", layer="strip_faces") as src:
        for feat in src:
            p = feat["properties"]
            for c in (p["left"], p["right"]):
                if 0 <= c < len(cells):
                    faces_of[c] += 1
    xmin, ymin, xmax, ymax = shapely.total_bounds(np.array(cells, dtype=object))
    with rasterio.open(ss.DEM) as src:
        win = from_bounds(xmin - 2, ymin - 2, xmax + 2, ymax + 2, src.transform).round_offsets().round_lengths()
        z = src.read(1, window=win).astype(np.float64)
        tr = src.window_transform(win)
        pix = src.res[0]
        z[z > 1e30] = np.nan
    owner = features.rasterize(((g, k) for k, g in enumerate(cells)), out_shape=z.shape, transform=tr, fill=-1, dtype="int32")
    inside = owner >= 0
    level_strip = np.array([p["level_end_m"] for p in props])
    s_strip = np.where(inside, level_strip[np.clip(owner, 0, None)], np.nan)
    level2, ltr, _t = ss.final_lattice_level(RUNS / "sq2")
    xs = tr.c + (np.arange(z.shape[1]) + 0.5) * tr.a
    ys = tr.f + (np.arange(z.shape[0]) + 0.5) * tr.e
    cols = np.clip(((xs - ltr.c) / ltr.a).astype(int), 0, level2.shape[1] - 1)
    rows = np.clip(((ys - ltr.f) / ltr.e).astype(int), 0, level2.shape[0] - 1)
    s_ref = level2[rows[:, None], cols[None, :]]
    w_strip = np.where(inside, np.clip(np.nan_to_num(s_strip - z, nan=0.0), 0.0, None), 0.0) * pix * pix
    w_ref = np.where(inside, np.clip(np.nan_to_num(s_ref - z, nan=0.0), 0.0, None), 0.0) * pix * pix
    n = len(cells)
    idx = np.clip(owner, 0, None).ravel()
    on = inside.ravel()
    v_strip = np.bincount(idx[on], weights=w_strip.ravel()[on], minlength=n)
    v_ref = np.bincount(idx[on], weights=w_ref.ravel()[on], minlength=n)
    wet_ref = np.bincount(idx[on], weights=((s_ref - z) > 0.01).ravel()[on].astype(float), minlength=n) * pix * pix
    # the mean reference surface over the cell's wet pixels, against the strip's flat level
    sref_sum = np.bincount(idx[on], weights=np.nan_to_num(np.where((s_ref - z) > 0.01, s_ref, 0.0)).ravel()[on], minlength=n)
    sref_mean = np.where(wet_ref > 0, sref_sum / np.maximum(wet_ref / (pix * pix), 1), np.nan)
    zmin = np.array([p["zmin_m"] for p in props])
    area = np.array([p["area_m2"] for p in props])
    kind = np.array([("pair" if p["kind"] == "corridor" and p["row"] == 0 else ("row" if p["kind"] == "corridor" else "band")) for p in props])
    main = chain_streams(read_thalwegs(W26))[0]["line"]
    cent = shapely.centroid(np.array(cells, dtype=object))
    along = shapely.line_locate_point(main, cent)
    off = shapely.distance(main, cent)
    out = {"run": name, "total": {"strip_m3": float(v_strip.sum()), "ref_m3": float(v_ref.sum()), "ratio": float(v_strip.sum() / v_ref.sum() - 1)}}
    print(f"{name}: water in the strip {v_strip.sum() / 1e3:.1f} e3 m3 against the 2 m squares' {v_ref.sum() / 1e3:.1f} ({100 * (v_strip.sum() / v_ref.sum() - 1):+.1f} %)")
    print("\nby kind of cell: cells, area km2, strip e3 m3, squares e3 m3, difference e3 m3, share of the total difference, level difference over wet cells m")
    total_diff = v_strip.sum() - v_ref.sum()
    out["by_kind"] = {}
    for k in ("pair", "row", "band"):
        m = kind == k
        if not m.any():
            continue
        d = v_strip[m].sum() - v_ref[m].sum()
        wetm = m & (wet_ref > 0)
        dl = float(np.nanmedian((level_strip - sref_mean)[wetm])) if wetm.any() else float("nan")
        out["by_kind"][k] = {"cells": int(m.sum()), "area_km2": float(area[m].sum() / 1e6), "strip": float(v_strip[m].sum()), "ref": float(v_ref[m].sum()), "diff": float(d), "level_median_m": dl}
        print(f"  {k:5s} {m.sum():6d} {area[m].sum() / 1e6:7.3f} {v_strip[m].sum() / 1e3:9.1f} {v_ref[m].sum() / 1e3:9.1f} {d / 1e3:+9.1f} {100 * d / total_diff:6.0f} %  {dl:+.3f}")
    print("\nalong the stem, 2 km bins: difference e3 m3 (pair / band), and the pair cells' median level difference m")
    out["along"] = []
    for a0 in range(4000, 20000, 2000):
        m = (along >= a0) & (along < a0 + 2000)
        mp, mb = m & (kind == "pair"), m & (kind == "band")
        dp = v_strip[mp].sum() - v_ref[mp].sum()
        db = v_strip[mb].sum() - v_ref[mb].sum()
        wetp = mp & (wet_ref > 0)
        dl = float(np.nanmedian((level_strip - sref_mean)[wetp])) if wetp.any() else float("nan")
        out["along"].append({"from_m": a0, "pair_diff": float(dp), "band_diff": float(db), "pair_level_m": dl, "pair_ref_m3": float(v_ref[mp].sum())})
        print(f"  {a0 / 1000:4.0f}-{(a0 + 2000) / 1000:<3.0f} km  pair {dp / 1e3:+7.1f} of {v_ref[mp].sum() / 1e3:6.1f}  band {db / 1e3:+7.1f} of {v_ref[mb].sum() / 1e3:6.1f}   pair level {dl:+.3f}")
    print("\nthe band by faces: cells, difference e3 m3, median level difference m")
    out["band_by_faces"] = {}
    for nfc in range(3, 13):
        m = (kind == "band") & (faces_of == nfc)
        if m.sum() < 20:
            continue
        d = v_strip[m].sum() - v_ref[m].sum()
        wetm = m & (wet_ref > 0)
        dl = float(np.nanmedian((level_strip - sref_mean)[wetm])) if wetm.any() else float("nan")
        out["band_by_faces"][nfc] = {"cells": int(m.sum()), "diff": float(d), "level_median_m": dl}
        print(f"  {nfc:2d} faces {m.sum():6d}  {d / 1e3:+8.1f}  {dl:+.3f}")
    print("\nthe pair cells by the share of the cell that is wet in the reference (a narrow channel in a wide cell is a small share)")
    out["pair_by_wet_share"] = []
    share = wet_ref / np.maximum(area, 1.0)
    for lo, hi in ((0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)):
        m = (kind == "pair") & (share >= lo) & (share < hi) & (wet_ref > 0)
        if not m.any():
            continue
        d = v_strip[m].sum() - v_ref[m].sum()
        dl = float(np.nanmedian((level_strip - sref_mean)[m]))
        out["pair_by_wet_share"].append({"share": [lo, hi], "cells": int(m.sum()), "diff": float(d), "ref": float(v_ref[m].sum()), "level_median_m": dl})
        print(f"  wet {lo:.2f}-{hi:.2f}: {m.sum():5d} cells, {d / 1e3:+7.1f} of {v_ref[m].sum() / 1e3:6.1f} e3 m3 ({100 * d / max(v_ref[m].sum(), 1):+5.1f} %), level {dl:+.3f} m")
    (OUT / f"{name}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ce20")
