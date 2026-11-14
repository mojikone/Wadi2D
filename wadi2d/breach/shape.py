"""The breach's shape in time and the published regressions that size it (W63). Pure functions, no grid.

Rules, after HEC-RAS's user-entered breach (USACE HEC, *Using HEC-RAS for Dam Break Studies*, TD-39, 2014, pp. 8-20):

- An overtopping breach starts at the dam top on its centre station; its bottom falls to the final bottom elevation and
  its bottom width grows from zero to the final width over the formation time, the side slopes fixed.
- A piping breach starts as a rectangular hole at the initial piping elevation; it grows down to the final bottom and
  as far up, and to the final bottom width. The roof falls in when the pool drops to the pipe's top (as HEC-RAS is
  reported to do; HEC does not publish its rule) or the pipe reaches the dam top, or at a pipe height over the breach
  height the user sets (Flood Modeller's collapse factor, default 0.6 there). From then on it is an open breach that
  keeps the pipe's bottom and width and grows on to the same final trapezoid.
- Progression: linear, or slow-fast-slow, ``(1 - cos(pi x)) / 2`` of the elapsed share x [Likely the shape of
  HEC-RAS's sine wave; its manual names it, not its formula].
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from wadi2d.config.constants import G
from wadi2d.config.schema import Breach, BreachEstimator


def progress(share: float, kind: str) -> float:
    """Formed share of the breach after ``share`` of the formation time."""
    x = min(max(share, 0.0), 1.0)
    return x if kind == "linear" else 0.5 * (1.0 - math.cos(math.pi * x))


@dataclass(frozen=True)
class Geometry:
    """The final breach; ``top`` is the dam top at the centre station."""

    centre: float
    top: float
    bottom: float
    width: float
    left: float
    right: float
    time: float


@dataclass(frozen=True)
class Opening:
    """The breach at one instant. ``roof`` is the pipe's top, ``inf`` for an open breach."""

    bottom: float
    width: float
    roof: float

    @property
    def open(self) -> bool:
        return math.isinf(self.roof)


def opening(geo: Geometry, f: float, mode: str, piping_z: float | None, collapsed: bool) -> Opening:
    """The breach at formed share ``f``."""
    if mode == "overtopping":
        return Opening(geo.top - f * (geo.top - geo.bottom), f * geo.width, math.inf)
    reach = piping_z - geo.bottom
    bottom = piping_z - f * reach
    roof = math.inf if collapsed else min(piping_z + f * reach, geo.top)
    return Opening(bottom, f * geo.width, roof)


def surface(geo: Geometry, cut: Opening, s: np.ndarray) -> np.ndarray:
    """Elevation of an open breach's surface at stations ``s`` along the dam line: the bottom over its width, the side
    slopes beyond; a vertical side (slope 0) stands at infinity."""
    s = np.asarray(s, dtype=np.float64)
    half = 0.5 * cut.width
    off = np.abs(s - geo.centre) - half
    slope = np.where(s < geo.centre, geo.left, geo.right)
    with np.errstate(divide="ignore", invalid="ignore"):
        rise = np.where(
            off <= 0.0, 0.0, np.where(slope > 0.0, off / np.where(slope > 0.0, slope, 1.0), np.inf)
        )
    return cut.bottom + rise


def opened_area(geo: Geometry, cut: Opening, level: float, ground: np.ndarray, s: np.ndarray) -> float:
    """Area below ``level`` between an open breach and the ground under it, sampled at stations ``s`` (equal spacing)."""
    z = np.maximum(ground, np.minimum(surface(geo, cut, s), geo.top))
    ds = float(s[1] - s[0])
    return float(np.sum(np.maximum(level - z, 0.0)) * ds)


@dataclass(frozen=True)
class Estimate:
    width: float
    slope: float
    time: float
    note: str


def _von_thun_cb(volume: float) -> float:
    for limit, cb in ((1.23e6, 6.1), (6.17e6, 18.3), (1.23e7, 42.7)):
        if volume < limit:
            return cb
    return 54.9


XU_ZHANG_REFERENCE_HEIGHT_M = 15.0
XU_ZHANG_UNIT_TIME_S = 3600.0
XU_ZHANG_WIDTH_MODE = {"overtopping": -1.207, "piping": -1.747}
XU_ZHANG_WIDTH_ERODIBILITY = {"high": -0.613, "medium": -1.073, "low": -1.268}
XU_ZHANG_TIME_ERODIBILITY = {"high": 0.038, "medium": 0.066, "low": 0.205}


def _froehlich_2016(est: BreachEstimator, mode: str, hb: float) -> Estimate:
    """Froehlich, D.C. (2016a), Empirical model of embankment dam breaching, River Flow 2016, as tabulated by West, Morris
    and Hassan (2018), *A guide to breach prediction*, HR Wallingford HRPP770, Appendix B: B_ave = 0.23 k_o V_w^(1/3),
    k_o 1.5 overtopping and 1.0 piping; side slopes 1.0 overtopping, 0.6 piping; t_f = 60 (V_w / (g h_b^2))^0.5 s
    (the guide's column says hours, but its Froehlich 2008 entry, 0.0176 h, is TD-39's 63.2 s: the 60 is seconds)."""
    ko = 1.5 if mode == "overtopping" else 1.0
    slope = 1.0 if mode == "overtopping" else 0.6
    bave = 0.23 * ko * est.pool_volume_m3 ** (1.0 / 3.0)
    time = 60.0 * math.sqrt(est.pool_volume_m3 / (G * hb * hb))
    return Estimate(max(bave - slope * hb, 0.0), slope, time, f"Froehlich (2016): B_ave {bave:.1f} m")


def _xu_zhang_2009(est: BreachEstimator, mode: str, hb: float, slope: float | None) -> Estimate:
    """Xu, Y. and Zhang, L.M. (2009), Breaching parameters for earth and rockfill dams, J. Geotech. Geoenviron. Eng.
    135(12), 1957-1970: the authors' best simplified models, as tabulated by West, Morris and Hassan (2018), HRPP770,
    Appendix B: B_ave / h_b = 5.543 (V_w^(1/3) / h_w)^0.739 exp(b4 + b5), b4 -1.207 overtopping and -1.747 piping,
    b5 -0.613, -1.073 and -1.268 for high, medium and low erodibility; t_f / 1 h = b5' (h_d / 15 m)^0.654
    (V_w^(1/3) / h_w)^1.246, b5' 0.038, 0.066 and 0.205. The simplified models give no side slope, which the job must,
    and no dam-type term: the full model's dam-type coefficients were not read from a citable source (W76)."""
    if slope is None:
        raise ValueError("Xu and Zhang (2009): its simplified models give no side slope; give left_slope and right_slope")
    vw = est.pool_volume_m3
    hw = est.water_depth_m if est.water_depth_m is not None else hb
    hd = est.dam_height_m if est.dam_height_m is not None else hb
    shape = vw ** (1.0 / 3.0) / hw
    exponent = XU_ZHANG_WIDTH_MODE[mode] + XU_ZHANG_WIDTH_ERODIBILITY[est.erodibility_class]
    bave = hb * 5.543 * shape**0.739 * math.exp(exponent)
    hours = XU_ZHANG_TIME_ERODIBILITY[est.erodibility_class] * (hd / XU_ZHANG_REFERENCE_HEIGHT_M) ** 0.654 * shape**1.246
    return Estimate(
        max(bave - slope * hb, 0.0), slope, hours * XU_ZHANG_UNIT_TIME_S,
        f"Xu and Zhang (2009), {est.erodibility_class} erodibility: B_ave {bave:.1f} m",
    )


def estimate(est: BreachEstimator, mode: str, height: float, slope: float | None = None) -> Estimate:
    """Final bottom width, side slope (H:V) and formation time (s) for a breach ``height`` m deep (HEC TD-39, 2014;
    Froehlich 2016 and Xu and Zhang 2009 in :func:`_froehlich_2016` and :func:`_xu_zhang_2009`). ``slope`` is the
    job's side slope, which only Xu and Zhang needs (it gives none) to turn B_ave into a bottom width.

    Froehlich (2008): B_ave = 0.27 K_o V_w^0.32 h_b^0.04, K_o 1.3 overtopping and 1.0 piping; t_f = 63.2 (V_w / (g h_b^2))^0.5
    s; side slopes 1.0 overtopping, 0.7 piping. MacDonald and Langridge-Monopolis (1984): V_er = 0.0261 (V_w h_w)^0.769
    (earthfill) or 0.00348 (V_w h_w)^0.852 (core or rockfill), t_f = 0.0179 V_er^0.364 h, slopes 0.5, bottom width from
    the eroded volume and the dam's section. Von Thun and Gillette (1990): B_ave = 2.5 h_w + C_b, slopes 1.0,
    t_f = 0.02 h_w + 0.25 h (resistant) or 0.015 h_w h (erodible). The bottom width is B_ave - slope h_b, at least 0.
    """
    vw, hb = est.pool_volume_m3, height
    hw = est.water_depth_m if est.water_depth_m is not None else hb
    if est.method == "froehlich_2016":
        return _froehlich_2016(est, mode, hb)
    if est.method == "xu_zhang_2009":
        return _xu_zhang_2009(est, mode, hb, slope)
    if est.method == "froehlich_2008":
        ko = 1.3 if mode == "overtopping" else 1.0
        slope = 1.0 if mode == "overtopping" else 0.7
        bave = 0.27 * ko * vw**0.32 * hb**0.04
        time = 63.2 * math.sqrt(vw / (G * hb * hb))
        return Estimate(max(bave - slope * hb, 0.0), slope, time, f"Froehlich (2008): B_ave {bave:.1f} m")
    if est.method == "macdonald_langridge_monopolis":
        slope = 0.5
        if est.dam_type == "earthfill":
            eroded = 0.0261 * (vw * hw) ** 0.769
        else:
            eroded = 0.00348 * (vw * hw) ** 0.852
        time = 0.0179 * eroded**0.364 * 3600.0
        c, z3 = est.crest_width_m, est.upstream_slope + est.downstream_slope
        width = (eroded - slope * hb * hb * (c + hb * z3 / 3.0)) / (hb * (c + hb * z3 / 2.0))
        return Estimate(
            max(width, 0.0), slope, time, f"MacDonald and Langridge-Monopolis (1984): eroded {eroded:.0f} m3"
        )
    slope = 1.0
    bave = 2.5 * hw + _von_thun_cb(vw)
    hours = 0.02 * hw + 0.25 if est.erodibility == "resistant" else 0.015 * hw
    return Estimate(
        max(bave - slope * hb, 0.0),
        slope,
        hours * 3600.0,
        f"Von Thun and Gillette (1990): B_ave {bave:.1f} m",
    )


def final_geometry(b: Breach, centre: float, top: float) -> tuple[Geometry, str | None]:
    """The final breach from the job, the estimator filling what the job leaves out; and what it estimated."""
    if b.bottom_z >= top:
        raise ValueError(f"breach of {b.dam}: bottom_z {b.bottom_z:g} m is not below the dam top {top:g} m")
    if b.mode == "piping" and b.piping_z >= top:
        raise ValueError(f"breach of {b.dam}: piping_z {b.piping_z:g} m is not below the dam top {top:g} m")
    width, left, right, time = b.bottom_width_m, b.left_slope, b.right_slope, b.formation_time_s
    note = None
    if b.estimator is not None:
        mean = 0.5 * (left + right) if left is not None and right is not None else None
        e =estimate(b.estimator, b.mode, top - b.bottom_z, mean)
        width = e.width if width is None else width
        left = e.slope if left is None else left
        right = e.slope if right is None else right
        time = e.time if time is None else time
        note = f"{e.note}; bottom width {width:.1f} m, side slopes {left:g} and {right:g} H:V, formation {time:.0f} s"
    return Geometry(centre, top, b.bottom_z, width, left, right, time), note
