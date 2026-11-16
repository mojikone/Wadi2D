"""How much of each dam's difference against W79 the dock's area-reduction rule explains (the coordinator's W103 note).

W79's hybrids read every lumped subbasin above a dam at the dam's own area (his rule, HMS's depth-area practice). The
dock's lumped curve reads each at the drainage area of the element where its water enters the grid (W98): in Hybrid
Lumped the outfall below the dam, so about the dam's area; in Hybrid 2D (each subbasin's water entering at its own
junction) the junction's area, smaller, so a larger factor and more rain. This reads the run's own record of that
(``lumped_entry_areas.json``), the generated basin's subbasins (area, CN) and gives per dam:

- the area-weighted factor the run applied, and the factor at the dam's area;
- the runoff those give by SCS (P = 251 mm x factor, Ia = 0.2 S, each subbasin's own CN), and their ratio: to first
  order the share of the inflow volume, and of the peak, that the rule adds.

Usage: ``s07_arf_rules.py <run folder> [out.json]``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
NUMBERS = json.loads((HERE / "inputs" / "storm_numbers.json").read_text(encoding="utf-8"))
DAMS = ("Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C", "HAT-J4")
DAM_KM2 = {"Bidah 03": 20.03, "Faydh 01": 74.42, "R5A": 117.12, "R2A": 175.94, "Z4C": 211.56, "HAT-J4": 260.36}
"""Each dam's own drainage area on the generated basins (session 1; HAT-J4 session 3): his rule reads every lumped
subbasin above a dam at this area."""


def factor(area: float) -> float:
    from wadi2d.storm.arf import ArfTable

    t = NUMBERS["arf_fm"]
    return ArfTable(t["areas_km2"], t["factors"], t["reduces_below_table"]).factor(area)


def runoff_mm(rain: float, cn: float) -> float:
    s = 25400.0 / cn - 254.0
    return 0.0 if rain <= 0.2 * s else (rain - 0.2 * s) ** 2 / (rain + 0.8 * s)


def main() -> None:
    run = Path(sys.argv[1])
    record = json.loads((run / "lumped_entry_areas.json").read_text(encoding="utf-8"))
    job = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
    model = json.loads(Path(job["hydrology"]["basin_json"]).read_text(encoding="utf-8"))
    els = {e["name"]: e for e in model["elements"]}

    def value(e, key):
        p = e["parameters"].get(key)
        return p.get("value") if isinstance(p, dict) else p

    def dam_of(name):
        n = els[name]["downstream"]
        while n is not None:
            hit = next(
                (d for d in DAMS if n in (d, f"{d} outfall") or n.startswith(f"{d} above") or (d == "HAT-J4" and n == "J6")),
                None,
            )
            if hit:
                return hit, n
            n = els[n]["downstream"]
        return None, None

    out = {}
    for row in record["subbasins"]:
        dam, node = dam_of(row["subbasin"])
        if dam is None:
            continue
        e = els[row["subbasin"]]
        d = out.setdefault(dam, {"subbasins": 0, "area_km2": 0.0, "f_area": 0.0, "q_run": 0.0, "q_dam": 0.0, "node": node})
        area, cn = value(e, "area_km2"), value(e, "curve_number")
        dam_area = DAM_KM2[dam]
        d["dam_area_km2"] = dam_area
        d["subbasins"] += 1
        d["area_km2"] += area
        d["f_area"] += row["factor"] * area
        d["q_run"] += runoff_mm(NUMBERS["depth_mm"] * row["factor"], cn) * area
        d["q_dam"] += runoff_mm(NUMBERS["depth_mm"] * factor(dam_area), cn) * area
    table = {}
    for dam, d in out.items():
        table[dam] = {
            "subbasins": d["subbasins"], "area_km2": round(d["area_km2"], 2), "dam_area_km2": round(d["dam_area_km2"], 2),
            "factor_applied_mean": round(d["f_area"] / d["area_km2"], 4), "factor_at_dam_area": round(factor(d["dam_area_km2"]), 4),
            "runoff_ratio": round(d["q_run"] / d["q_dam"], 4),
        }  # fmt: skip
    text = json.dumps(table, indent=1)
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
