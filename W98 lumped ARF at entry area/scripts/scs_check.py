"""W98 task 2: the NRCS 24-hour distributions W95 typed from memory, against HEC-HMS 4.12's own tables.

HEC-HMS 4.12 holds the four distributions in ``hms.jar`` (class ``hms/model/met/e/aT``, the same arrays again in
``aV``) as 1441 ordinates, one a minute over 24 hours. Every sixth ordinate (0.1 h) is a number of four decimals, the
NRCS tabular 0.1-hour distribution; between them HMS's minutes lie on a natural cubic spline through those knots, to
5e-5. Which array is which type is read off its ordinates (Type I 0.035 at 2 h, IA 0.425 at 8 h, II 0.663 at 12 h, III
0.500 at 12 h).

What this writes:
- ``results/scs_hms_4_12_minutes.csv``: HMS's 1441 ordinates of each type;
- ``results/scs_w95_against_hms.csv``: each of W95's 23 ordinates against HMS's, and each type's largest difference;
- ``results/scs_new_against_hms.json``: the corrected curve (the 0.1-hour knots, a natural spline to the minute)
  against HMS's every minute;
- with ``--write``, ``wadi2d/storm/scs_tables.py``, the 0.1-hour knots of each type.

Run from the repository root: ``.venv\\Scripts\\python "W98 lumped ARF at entry area\\scripts\\scs_check.py" [--write]``.
"""

from __future__ import annotations

import csv
import json
import sys
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

import java_arrays  # noqa: E402

JAR = Path(r"C:\Program Files\HEC\HEC-HMS\4.12\hms.jar")
MEMBER = "hms/model/met/e/aT.class"
OUT = HERE.parent / "results"
MODULE = ROOT / "wadi2d" / "storm" / "scs_tables.py"
MINUTES = 1441
KNOT_EVERY = 6
SIGNATURE = {"I": (120, 0.035), "IA": (480, 0.425), "II": (720, 0.663), "III": (720, 0.500)}
"""The minute and ordinate that tell the types apart."""
W95_HOURS = (0, 2, 4, 6, 7, 8, 8.5, 9, 9.5, 9.75, 10, 10.5, 11, 11.5, 11.75, 12, 12.5, 13, 13.5, 14, 16, 20, 24)
W95_CURVES = {
    "I": (0, .035, .076, .125, .156, .194, .219, .254, .303, .362, .515, .583, .624, .654, .669, .682, .706, .727,
          .748, .767, .830, .926, 1.0),
    "IA": (0, .050, .116, .206, .268, .425, .480, .520, .550, .564, .577, .601, .624, .645, .655, .664, .683, .701,
           .719, .736, .800, .906, 1.0),
    "II": (0, .022, .048, .080, .098, .120, .133, .147, .163, .172, .181, .204, .235, .283, .357, .663, .735, .772,
           .799, .820, .880, .952, 1.0),
    "III": (0, .020, .043, .072, .089, .115, .130, .148, .167, .178, .189, .216, .250, .298, .339, .500, .702, .751,
            .785, .811, .886, .957, 1.0),
}  # fmt: skip
"""The 23 ordinates W95 typed from memory (``wadi2d/storm/patterns.py`` at ``0cfc332``), kept here as checked."""


def hms_tables() -> dict[str, np.ndarray]:
    b = zipfile.ZipFile(JAR).read(MEMBER)
    cp, i = java_arrays.pool(b)
    arrays = []
    for _name, attrs in java_arrays.methods(b, cp, i):
        for kind, data in attrs:
            if kind == "Code":
                arrays += [a for a in java_arrays.arrays(data, cp) if a["size"] == MINUTES]
    found = {}
    for a in arrays:
        values = np.array([a["values"].get(k, 0.0) for k in range(MINUTES)])
        for kind, (minute, ordinate) in SIGNATURE.items():
            if abs(values[minute] - ordinate) < 5e-4 and kind not in found:
                if kind == "II" and abs(values[480] - 0.120) > 5e-4:
                    continue
                found[kind] = values
                break
    if set(found) != set(SIGNATURE):
        raise SystemExit(f"found {sorted(found)} in {MEMBER}, not the four types")
    return found


def main(write: bool) -> None:
    from scipy.interpolate import CubicSpline

    hms = hms_tables()
    OUT.mkdir(exist_ok=True)
    with (OUT / "scs_hms_4_12_minutes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["minute", *hms])
        for m in range(MINUTES):
            w.writerow([m, *(f"{hms[k][m]:.8f}" for k in hms)])
    old_hours, old_curves = W95_HOURS, W95_CURVES
    rows, worst = [], {}
    for kind, values in hms.items():
        for hour, mine in zip(old_hours, old_curves[kind], strict=True):
            theirs = float(values[int(round(hour * 60))])
            rows.append({"type": kind, "hour": hour, "w95": mine, "hms_4_12": round(theirs, 6), "diff": round(mine - theirs, 6)})
        worst[kind] = max((r for r in rows if r["type"] == kind), key=lambda r: abs(r["diff"]))
    with (OUT / "scs_w95_against_hms.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    minutes = np.arange(MINUTES, dtype=np.float64)
    knots = {kind: np.round(values[::KNOT_EVERY], 4) for kind, values in hms.items()}
    new = {}
    for kind, k in knots.items():
        spline = CubicSpline(minutes[::KNOT_EVERY], k, bc_type="natural")(minutes)
        new[kind] = {
            "knots_exactly_four_decimals": bool(np.abs(hms[kind][::KNOT_EVERY] - k).max() == 0.0),
            "spline_worst_against_hms": float(np.abs(spline - hms[kind]).max()),
            "linear_between_knots_worst_against_hms": float(np.abs(np.interp(minutes, minutes[::KNOT_EVERY], k) - hms[kind]).max()),
            "w95_worst": {"hour": worst[kind]["hour"], "w95": worst[kind]["w95"], "hms": worst[kind]["hms_4_12"],
                          "diff": worst[kind]["diff"]},
            "w95_ordinates_off_by_more_than_0.0005": sum(1 for r in rows if r["type"] == kind and abs(r["diff"]) > 5e-4),
        }  # fmt: skip
    (OUT / "scs_new_against_hms.json").write_text(json.dumps(new, indent=1), encoding="utf-8")
    print(json.dumps(new, indent=1))
    if write:
        MODULE.write_text(_module(knots), encoding="utf-8")
        print(f"wrote {MODULE}")


def _module(knots: dict[str, np.ndarray]) -> str:
    lines = [
        '"""The NRCS 24-hour rainfall distributions, Types I, IA, II and III, at every 0.1 hour (W98).',
        "",
        "Source: HEC-HMS 4.12, ``hms.jar``, class ``hms/model/met/e/aT``, the tables its SCS Storm uses: 1441 ordinates a",
        "minute, every sixth of them (0.1 h) a number of four decimals, the NRCS tabular distribution; HMS's minutes",
        "between them lie on a natural cubic spline through these knots, to 5e-5. Written by",
        '``W98 lumped ARF at entry area/scripts/scs_check.py --write``; the 23 ordinates W95 typed from memory were up to',
        "0.0285 off (Type II at 11.75 h).",
        '"""',
        "",
        "SCS_KNOT_HOURS = 0.1",
        '"""The step of the tables, hours: 241 ordinates from 0 to 24 h."""',
        "SCS_KNOTS = {",
    ]
    for kind, values in knots.items():
        lines.append(f'    "{kind}": (')
        text = [f"{v:.4f}".rstrip("0").rstrip(".") if v not in (0.0, 1.0) else f"{v:.1f}" for v in values]
        for start in range(0, len(text), 12):
            lines.append("        " + ", ".join(text[start : start + 12]) + ",")
        lines.append("    ),")
    lines += ["}  # fmt: skip", '"""Fraction of the 24-hour depth fallen by each 0.1 hour, by NRCS type."""', ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main("--write" in sys.argv)
