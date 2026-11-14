"""Test 1, identical rain: every element's series of a Basin 3 depth-area analysis against HMS's own DSS.

For each analysis point the engine reruns the sub-network above it with HMS's storm at that point's area (the FM
storm and the ARF FM table through the point's drainage area, exactly as the depth-area analysis does), and every
element above the point is compared with the DSS record HMS wrote for that point: outflow of every subbasin,
junction, reach and reservoir; for a reservoir also its inflow, storage and pool level. Reads a copy of the DSS.

Usage: python series_check.py "<analysis>" <dss copy> <out.csv>
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

from wadi2d.hms import daa_fpart, load_nals, open_dss
from wadi2d.hms.dss import DssLookupError
from wadi2d.hydrology.depth_area import analyse_point
from wadi2d.hydrology.model import Reservoir
from wadi2d.hydrology.replication import _Project, _point_storm  # noqa: PLC2701 - the replication's own wiring
from wadi2d.hydrology.from_hms import grid_from_hms
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.reservoir import ReservoirOutflowCurve

HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.hms")
THOUSAND = 1000.0


def pool(routing: ReservoirOutflowCurve, inflow: np.ndarray, outflow: np.ndarray, dt_s: float):
    """Storage and level by the step's own mass balance, which Modified Puls holds exactly."""
    start = float(np.interp(routing.initial_elevation_m, routing.elevations_m, routing.storage_m3))
    change = np.concatenate(([0.0], np.cumsum(0.5 * (inflow[1:] + inflow[:-1] - outflow[1:] - outflow[:-1]) * dt_s)))
    storage = start + change
    return storage, np.interp(storage, routing.storage_m3, routing.elevations_m)


def main(analysis_name: str, dss_path: str, out: str) -> None:
    project = _Project(HMS)
    analysis = load_nals(HMS.with_suffix(".nals")).analysis(analysis_name)
    hms_basin, engine = project.model(analysis.basin_model_name)
    basin_path = project.project.path_of(project.project.basins[analysis.basin_model_name])
    met_path = project.project.path_of(project.project.mets[analysis.met_model_name])
    storm = _point_storm(met_path, project.tables, hms_basin, engine.basin, basin_path, HMS.stem)
    grid = grid_from_hms(analysis)
    dt_s = grid.dt_minutes * SECONDS_PER_MINUTE
    rows = []
    with open_dss(dss_path) as dss:
        for point in analysis.points:
            result = analyse_point(engine, storm, grid, point)
            fpart = daa_fpart(analysis.name, point)
            for name, flow in result.run.outflow.items():
                element = engine.basin.elements[name]
                series = {"FLOW": flow}
                if isinstance(element, Reservoir):
                    inflow = result.run.inflow[name]
                    storage, level = pool(element.routing, inflow, flow, dt_s)
                    series |= {"FLOW-COMBINE": inflow, "STORAGE": storage / THOUSAND, "ELEVATION": level}
                for part, mine in series.items():
                    try:
                        hms = dss.read_timeseries(name, part, fpart).values
                    except DssLookupError:
                        continue
                    mine = mine[-len(hms):]
                    scale = max(float(np.abs(hms).max()), 1e-12)
                    rows.append({
                        "point": point, "element": name, "series": part, "kind": type(element).__name__,
                        "hms_max": float(hms.max()), "wadi2d_max": float(mine.max()),
                        "peak_error_percent": 100.0 * (mine.max() / hms.max() - 1.0) if hms.max() else 0.0,
                        "max_abs_diff": float(np.abs(mine - hms).max()),
                        "max_rel_diff": float(np.abs(mine - hms).max() / scale),
                        "hms_sum": float(hms.sum()), "wadi2d_sum": float(mine.sum()),
                        "peak_step_error": int(np.argmax(mine)) - int(np.argmax(hms)),
                    })
    with open(out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(analysis_name, "series compared:", len(rows))
    for part in ("FLOW", "FLOW-COMBINE", "STORAGE", "ELEVATION"):
        chosen = [r for r in rows if r["series"] == part]
        if not chosen:
            continue
        worst = max(chosen, key=lambda r: r["max_rel_diff"])
        worst_peak = max(chosen, key=lambda r: abs(r["peak_error_percent"]))
        print(f"  {part}: n={len(chosen)} worst series {worst['max_rel_diff']:.2e} of peak at {worst['element']}"
              f" ({worst['point']}); worst peak {worst_peak['peak_error_percent']:+.4f} % at {worst_peak['element']}"
              f" ({worst_peak['point']}); max step slip {max(abs(r['peak_step_error']) for r in chosen)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
