"""Candidate laws for the dam top, the rating spillway, the seepage and the evaporation against HMS's own series."""

from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "tests" / "data" / "hms_structures"
RATING_Z = np.array([100.0, 106.0, 107.0, 108.0, 110.0, 112.0, 115.0, 120.0, 125.0])
RATING_Q = np.array([0.0, 0.0, 5.0, 20.0, 80.0, 180.0, 380.0, 800.0, 1300.0])
TOP, LENGTH, C = 109.5, 150.0, 1.7
EVAPORATION_MM = [300.0, 450.0]


def load(case):
    names = (DATA / f"{case}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    data = np.loadtxt(DATA / f"{case}.csv", delimiter=",", skiprows=1)
    return {name: data[:, k] for k, name in enumerate(names)}


def report(label, model, hms):
    worst = int(np.argmax(np.abs(model - hms)))
    print(f"  {label}: max |d| {np.abs(model - hms).max():.3e} at {worst} (model {model[worst]:.6f} hms {hms[worst]:.6f})")


for case in ("rating", "level_dam", "level_dam_tw", "all"):
    s = load(case)
    z = s["elevation_m"]
    print(case, "z max", z.max())
    report("rating", np.interp(z, RATING_Z, RATING_Q), s["spill_1"])
    if "damtop_1" in s:
        free = C * LENGTH * np.maximum(z - TOP, 0.0) ** 1.5
        report("dam top free", free, s["damtop_1"])
        if "tailwater_m" in s:
            tw = s["tailwater_m"]
            drowned = C * LENGTH * np.maximum(z - np.maximum(TOP, tw), 0.0) ** 1.5
            report("dam top head to max(top, tw)", drowned, s["damtop_1"])
            report("dam top min(free, head to tw)", np.minimum(free, drowned), s["damtop_1"])

for case in ("seepage", "seepage_tw", "seepage_in", "all"):
    s = load(case)
    z = s["elevation_m"]
    tw = s.get("tailwater_m", np.full_like(z, 100.0))
    out_q = np.interp(z - tw, [0.0, 5.0, 10.0, 25.0], [0.0, 0.5, 1.5, 6.0])
    in_q = np.interp(tw - z, [0.0, 5.0, 25.0], [0.0, 0.2, 1.0])
    print(case, "tw", tw.min(), tw.max())
    report("seepage out(z - tw)", out_q, s["seepage"])
    report("seepage out(z - 100)", np.interp(z - 100.0, [0.0, 5.0, 10.0, 25.0], [0.0, 0.5, 1.5, 6.0]), s["seepage"])
    report("seepage out(z - tw) - in(tw - z)", out_q - in_q, s["seepage"])

for case in ("evaporation", "all"):
    s = load(case)
    area = s["area_m2"]
    vol = s["evaporation_m3"]
    hours = np.arange(len(area)) * 5.0 / 60.0
    month = np.where(hours < 12.0, 0, 1)  # 31 Jan 12:00 + 12 h = 1 Feb 00:00
    days = np.where(month == 0, 31.0, 29.0)
    rate = np.array(EVAPORATION_MM)[month] / 1000.0 / (days * 288.0)  # m per 5-min step
    for label, a in (("area at end of step", area), ("mean area of step", np.concatenate(([area[0]], 0.5 * (area[1:] + area[:-1]))))):
        model = rate * a
        model[0] = 0.0
        report(f"evaporation month/steps x {label}", model, vol)
    month_start = np.where(hours <= 12.0, 0, 1)
    model = np.array(EVAPORATION_MM)[month_start] / 1000.0 / (np.where(month_start == 0, 31.0, 29.0) * 288.0) * area
    model[0] = 0.0
    report("evaporation, step ending on 1 Feb 00:00 in January", model, vol)
