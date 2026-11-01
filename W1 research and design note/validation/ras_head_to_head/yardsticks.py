"""How far apart are RAS and RAS? The spread that gives the Wadi2D difference its meaning.

usage: yardsticks.py
Compares pairs of runs on max level, peak discharge and pixel extent:
  RAS SWE-EM against RAS SWE-ELM at the same cell size; RAS against itself at a shorter step;
  each model against itself between cell sizes, on the 20 m lattice (the 10 m cells of a 20 m cell, averaged).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np

import case
from compare_results import Ras, Wadi, pixel_extent, stats


WET = 0.02  # a cell shallower than this counts as dry in the averages, m


def coarsen(a: np.ndarray, how=np.nanmean) -> np.ndarray:
    """2 x 2 cells to one, over the wet ones only; a cell with none stays NaN."""
    n = a.shape[0] // 2
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return how(a[: 2 * n, : 2 * n].reshape(n, 2, n, 2), axis=(1, 3))


def peaks(run) -> dict[str, float]:
    if isinstance(run, Ras):
        return {k: float(run.section_flow(*v).max()) for k, v in case.SECTIONS.items()}
    return {k: float(run.series(k)[1].max()) for k in case.SECTIONS}


def level_of(run) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(run, Ras):
        d = run.wse_max - run.zmin
        return np.where(d > WET, run.wse_max, np.nan), np.where(d > WET, d, np.nan)
    return np.where(run.depth > WET, run.level, np.nan), np.where(run.depth > WET, run.depth, np.nan)


def pair(a, b, dx: float, label: str, coarse: tuple[bool, bool] = (False, False)) -> dict:
    la, da = level_of(a)
    lb, db = level_of(b)
    if coarse[0]:
        la, da = coarsen(la), coarsen(da, np.nanmax)
    if coarse[1]:
        lb, db = coarsen(lb), coarsen(db, np.nanmax)
    deep = (da >= 0.5) & (db >= 0.5)
    pa = pixel_extent(la, dx, 0.1)
    pb = pixel_extent(lb, dx, 0.1)
    qa, qb = peaks(a), peaks(b)
    out = {
        "label": label,
        "level_second_minus_first_deep_m": stats((lb - la)[deep]),
        "pixel_F_0.1": float((pa & pb).sum() / max((pa | pb).sum(), 1)),
        "area_km2": [float(pa.sum() * 0.25e-6), float(pb.sum() * 0.25e-6)],
        "peak_diff_pct": {k: float(100 * (qb[k] / qa[k] - 1)) for k in qa},
    }
    s = out["level_second_minus_first_deep_m"]
    print(f"{label:58s} dlevel mean {s['mean']:+.3f} rms {s['rms']:.3f}  F {out['pixel_F_0.1']:.3f}  "
          f"peaks {[round(v, 2) for v in out['peak_diff_pct'].values()]}")  # fmt: skip
    return out


def main() -> None:
    res = []
    r20 = Ras(Path("ras_20m_swe_em"), 20.0)
    r10 = Ras(Path("ras_10m_swe_em"), 10.0)
    e20 = Ras(Path("ras_20m_swe_elm"), 20.0)
    w20 = Wadi(Path("wadi_runs/w20m"), 150, 20.0)
    w10 = Wadi(Path("wadi_runs/w10m"), 300, 10.0)
    res.append(pair(r20, e20, 20.0, "RAS 20 m: SWE-EM -> SWE-ELM"))
    if Path("ras_10m_swe_elm/Fan.p01.hdf").exists():
        res.append(pair(r10, Ras(Path("ras_10m_swe_elm"), 10.0), 10.0, "RAS 10 m: SWE-EM -> SWE-ELM"))
    if Path("ras_20m_swe_em_dt1s/Fan.p01.hdf").exists():
        res.append(pair(r20, Ras(Path("ras_20m_swe_em_dt1s"), 20.0), 20.0, "RAS 20 m SWE-EM: Courant step -> fixed 1 s"))
    res.append(pair(r20, w20, 20.0, "RAS 20 m SWE-EM -> Wadi2D 20 m"))
    res.append(pair(r10, w10, 10.0, "RAS 10 m SWE-EM -> Wadi2D 10 m"))
    res.append(pair(r20, r10, 20.0, "RAS SWE-EM: 20 m -> 10 m (10 m averaged to 20 m)", (False, True)))
    res.append(pair(w20, w10, 20.0, "Wadi2D: 20 m -> 10 m (10 m averaged to 20 m)", (False, True)))
    Path("yardsticks.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
