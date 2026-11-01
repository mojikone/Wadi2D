"""A copy of a grid cache whose face conveyance is RAS's single-section form, K = A (A/W)^(2/3) / n.

usage: make_hec_conveyance_cache.py SRC_CACHE_FILE DST_FOLDER --n 0.04

Wadi2D integrates conveyance across the face, strip by strip; RAS takes one hydraulic radius for the whole face.
wadi2d/ has no switch for this (N03 recommendation 2 asked for one), so the experiment edits a cached table and
leaves the package alone. W = dA/de comes from the area column. The run reads this file as a cache hit.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import h5py
import numpy as np


def single_section(tab: np.ndarray, top: np.ndarray, n: float) -> np.ndarray:
    """tab (..., rows, 2), top (...): area and K^0.6 at e = top (r/last)^2. Returns the new K^0.6 column."""
    rows = tab.shape[-2]
    grid = (np.arange(rows) / (rows - 1)) ** 2
    e = top[..., None] * grid
    a = tab[..., 0].astype(np.float64)
    w = np.gradient(a, axis=-1) / np.maximum(np.gradient(e, axis=-1), 1e-12)
    w = np.maximum(w, 1e-9)
    k = a * (a / w) ** (2.0 / 3.0) / n
    return k**0.6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst_folder")
    ap.add_argument("--n", type=float, default=0.04)
    a = ap.parse_args()
    src = Path(a.src)
    dst = Path(a.dst_folder) / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    with h5py.File(dst, "r+") as f:
        for tab, top in (("ftabx", "efx"), ("ftaby", "efy")):
            d = f[tab]
            t = d[()]
            before = t[..., 1].copy()
            t[..., 1] = single_section(t, f[top][()], a.n).astype(np.float32)
            d[...] = t
            big = before > 1.0
            print(tab, "K ratio strips / single, median", float(np.median((before[big] / np.maximum(t[..., 1][big], 1e-9)) ** (5 / 3))))
    print("written", dst)


if __name__ == "__main__":
    main()
