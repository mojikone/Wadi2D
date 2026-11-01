"""How big is the difference between the two codes, against RAS's own solver-to-solver spread, at 20 m.

Writes yardsticks.json. Levels are max levels on the same lattice, in the wadi class of compare.py.
"""

from __future__ import annotations

import json

import numpy as np
from scipy import ndimage

import case
from compare import Lattice, Ras, Wadi, cell_classes, pixel_wet, stats

out: dict = {}


def wadi_class(lat: Lattice) -> np.ndarray:
    acc, _ = cell_classes(lat)
    return ndimage.binary_dilation(acc >= case.WADI_KM2, iterations=max(1, round(40.0 / lat.dx))) & lat.mask


def fan_f(a: np.ndarray, b: np.ndarray, lat: Lattice, th: float) -> float:
    c = round((case.FAN_WEST - case.X0) / 0.5)
    pa, pb = pixel_wet(a, lat, th)[:, c:], pixel_wet(b, lat, th)[:, c:]
    return float((pa & pb).sum() / max((pa | pb).sum(), 1))


lat20 = Lattice(20.0)
w20 = wadi_class(lat20)
r_em = Ras("20m_n050_em", lat20)
r_elm = Ras("20m_n050_elm", lat20)
d = r_elm.wse_max - r_em.wse_max
de = (r_em.wse_max - r_em.zmin >= 0.5) & (r_elm.wse_max - r_elm.zmin >= 0.5)
wad = Wadi("20m_n050_em", lat20)
out["ras_20m_em_to_elm"] = {"wadi_deep_level_m": stats(d[w20 & de]), "fan_F_0.3": fan_f(r_em.wse_max, r_elm.wse_max, lat20, 0.3)}
d = wad.level - r_em.wse_max
de2 = de & (wad.depth >= 0.5)
out["wadi2d_to_ras_em_20m"] = {"wadi_deep_level_m": stats(d[w20 & de2]), "fan_F_0.3": fan_f(r_em.wse_max, wad.level, lat20, 0.3)}
d = wad.level - r_elm.wse_max
out["wadi2d_to_ras_elm_20m"] = {"wadi_deep_level_m": stats(d[w20 & de2]), "fan_F_0.3": fan_f(r_elm.wse_max, wad.level, lat20, 0.3)}

(case.HERE / "yardsticks.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
