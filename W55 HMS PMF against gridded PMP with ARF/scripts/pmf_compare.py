"""Test 2, the comparison: HMS's lumped-depth runs (``_work/hms_project/W55_PMP_<dam>.dss``) against Wadi2D.

For each dam: HMS's reservoir inflow, outflow, level and storage, and the catchment rain it logged; Wadi2D with the
same lumped storm (the code check of the set-up, series against series); Wadi2D on the distributed grid with ARF (c)
and without (d); HMS's own PMF (a) and Wadi2D's replication of it (b). Writes ``results/pmf_compare.json`` and prints
the table of the README.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from wadi2d.hms import open_dss
from wadi2d.hydrology.depth_area import analyse_point, point_storm
from wadi2d.hydrology.from_hms import grid_from_hms
from wadi2d.hydrology.replication import _Project
from wadi2d.hms import load_nals
from wadi2d.storm import HypotheticalStorm, PercentPattern

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE / "_work" / "hms_project"
HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.hms")
THOUSAND = 1000.0
DT_MIN = 5.0


def summary(inflow, outflow, level, storage):
    dt_s = DT_MIN * 60.0
    return {
        "inflow_peak": float(inflow.max()), "inflow_peak_h": float(np.argmax(inflow)) * DT_MIN / 60.0,
        "outflow_peak": float(outflow.max()), "outflow_peak_h": float(np.argmax(outflow)) * DT_MIN / 60.0,
        "inflow_volume_Mm3": float(np.trapezoid(inflow)) * dt_s / 1e6,
        "outflow_volume_Mm3": float(np.trapezoid(outflow)) * dt_s / 1e6,
        "max_level_m": float(level.max()), "max_storage_Mm3": float(storage.max()) / 1e6,
    }


def main() -> None:
    inputs = json.loads((HERE / "results" / "pmf_inputs.json").read_text(encoding="utf-8"))
    wadi = json.loads((HERE / "results" / "pmf_wadi2d.json").read_text(encoding="utf-8"))
    project = _Project(HMS)
    _, engine = project.model("Basin 3")
    grid = grid_from_hms(load_nals(HMS.with_suffix(".nals")).analysis("DA PMP B3"))
    arf = project.tables.area_reductions["ARF FM"]
    out = {}
    for dam, row in inputs.items():
        reservoir = f"{dam} Reservoir"
        stem = "W55_PMP_" + dam.replace(" ", "_")
        fpart = f"RUN:W55 PMP {dam}"
        with open_dss(PROJECT / f"{stem}.dss") as dss:
            hms = {part: dss.read_timeseries(reservoir, part, fpart).values
                   for part in ("FLOW-COMBINE", "FLOW", "ELEVATION", "STORAGE")}
        log = (PROJECT / f"{stem}.log").read_text(errors="replace")
        reduced = float(re.search(r"Area-reduced hypothetical storm depth: ([\d,.]+) mm", log).group(1).replace(",", ""))
        hms_row = summary(hms["FLOW-COMBINE"], hms["FLOW"], hms["ELEVATION"], hms["STORAGE"] * THOUSAND)
        # The same lumped storm in Wadi2D, series against HMS's series.
        storm = HypotheticalStorm(
            depth_mm=row["grid_depth_mm"],
            pattern=PercentPattern(np.asarray(row["pattern_time_percent"]), np.asarray(row["pattern_depth_percent"])),
            duration_hours=row["duration_h"], storm_area_km2=row["drainage_area_km2"], arf=arf)
        result = analyse_point(engine, point_storm(storm), grid, reservoir)
        n = len(hms["FLOW"])
        inflow, outflow = result.run.inflow[reservoir][-n:], result.outflow[-n:]
        storage, level = engine.basin.elements[reservoir].routing.pool(inflow, outflow, DT_MIN)
        check = {
            "rain_mm": float(storm.at_area(row["drainage_area_km2"]).total_depth),
            "inflow_max_abs_diff": float(np.abs(inflow - hms["FLOW-COMBINE"]).max()),
            "outflow_max_abs_diff": float(np.abs(outflow - hms["FLOW"]).max()),
            "level_max_abs_diff_m": float(np.abs(level - hms["ELEVATION"]).max()),
            "outflow_peak_error_percent": 100.0 * (outflow.max() / hms["FLOW"].max() - 1.0),
        }
        out[dam] = {"area_km2": row["drainage_area_km2"], "arf": row["arf"], "grid_depth_mm": row["grid_depth_mm"],
                    "hms_lumped_arf": hms_row | {"rain_mm": reduced}, "wadi2d_same_storm": check,
                    **wadi[dam]}
    (HERE / "results" / "pmf_compare.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    keys = [("a/b HMS FM PMP", "b_fm_pmp"), ("HMS lumped grid depth + ARF", "hms_lumped_arf"),
            ("Wadi2D grid distributed + ARF", "c_grid_arf"), ("Wadi2D grid distributed, no ARF", "d_grid_no_arf")]
    for dam, row in out.items():
        c = row["wadi2d_same_storm"]
        print(f"{dam}: A {row['area_km2']:.2f} km2, ARF {row['arf']:.4f}, grid {row['grid_depth_mm']:.1f} mm; "
              f"Wadi2D on HMS's lumped storm: dQin {c['inflow_max_abs_diff']:.2e} dQout {c['outflow_max_abs_diff']:.2e}"
              f" dz {c['level_max_abs_diff_m']:.1e}")
        for label, key in keys:
            r = row[key]
            print(f"   {label:32s} rain {r['rain_mm']:7.1f} in {r['inflow_peak']:7.1f} @{r['inflow_peak_h']:5.2f} out "
                  f"{r['outflow_peak']:7.1f} @{r['outflow_peak_h']:5.2f} Vin {r['inflow_volume_Mm3']:6.2f} Vout "
                  f"{r['outflow_volume_Mm3']:6.2f} lvl {r['max_level_m']:.3f}")


if __name__ == "__main__":
    main()
