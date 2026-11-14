"""The README's tables from results/*.json, printed as Markdown."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "results"

reservoirs = json.loads((HERE / "reservoirs.json").read_text(encoding="utf-8"))
print("| Run | Dam | Peak inflow | Peak outflow | Attenuation % | Peaks at, h (in / out) | Volume in / out, Mm3 |"
      " Max pool, m | Wadi2D chain: max outflow diff, m3/s | max level diff, m |")
print("|---|---|---|---|---|---|---|---|---|---|")
for run, dams in reservoirs.items():
    for dam, r in dams.items():
        h = r["hms"]
        print(f"| {run} | {dam} | {h['inflow_peak']:,.1f} | {h['outflow_peak']:,.1f} | {h['attenuation_percent']:.1f} |"
              f" {h['inflow_peak_h']:.2f} / {h['outflow_peak_h']:.2f} | {h['inflow_volume_Mm3']:.2f} /"
              f" {h['outflow_volume_Mm3']:.2f} | {h['max_level_m']:.3f} | {r['chain']['outflow_max_abs_diff']:.0e} |"
              f" {r['chain']['level_max_abs_diff_m']:.0e} |")

compare = json.loads((HERE / "pmf_compare.json").read_text(encoding="utf-8"))
print()
print("| Dam | Area, km2 | ARF at the area | Case | Rain over the catchment, mm | Peak inflow, m3/s | at, h |"
      " Peak outflow, m3/s | at, h | Inflow volume, Mm3 | Outflow volume, Mm3 | Max pool, m |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
cases = [("(a)=(b) HMS PMF, FM PMP storm", "b_fm_pmp"), ("HMS, grid depth lumped + ARF", "hms_lumped_arf"),
         ("(c) Wadi2D, grid distributed + ARF", "c_grid_arf"), ("(d) Wadi2D, grid distributed, no ARF", "d_grid_no_arf"),
         ("split: grid depth + ARF on the FM PMP pattern", "f_grid_depth_fm_pattern")]
for dam, row in compare.items():
    for label, key in cases:
        r = row[key]
        print(f"| {dam} | {row['area_km2']:.2f} | {row['arf']:.4f} | {label} | {r['rain_mm']:,.1f} |"
              f" {r['inflow_peak']:,.1f} | {r['inflow_peak_h']:.2f} | {r['outflow_peak']:,.1f} | {r['outflow_peak_h']:.2f} |"
              f" {r['inflow_volume_Mm3']:.2f} | {r['outflow_volume_Mm3']:.2f} | {r['max_level_m']:.3f} |")
print()
print("| Dam | HMS lumped + ARF: peak in / out | Wadi2D distributed + ARF: peak in / out | difference in / out, % |"
      " pool, m | Wadi2D on HMS's own lumped storm: max diff in / out, m3/s |")
print("|---|---|---|---|---|---|")
for dam, row in compare.items():
    h, c, s = row["hms_lumped_arf"], row["c_grid_arf"], row["wadi2d_same_storm"]
    print(f"| {dam} | {h['inflow_peak']:,.1f} / {h['outflow_peak']:,.1f} | {c['inflow_peak']:,.1f} / {c['outflow_peak']:,.1f} |"
          f" {100 * (c['inflow_peak'] / h['inflow_peak'] - 1):+.2f} / {100 * (c['outflow_peak'] / h['outflow_peak'] - 1):+.2f} |"
          f" {c['max_level_m'] - h['max_level_m']:+.3f} | {s['inflow_max_abs_diff']:.0e} / {s['outflow_max_abs_diff']:.0e} |")
