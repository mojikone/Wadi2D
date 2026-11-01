"""The forcing of both models and the HMS-equivalent hydrograph.

The 100-yr Block 2 storm at the storm area of the Bidah job (20.971 km2), through S13's SCS losses in the lumped
engine, gives one excess hyetograph on 5 min steps. RAS takes it as a period-ending table, Wadi2D as a hypothetical
storm with no ARF and no losses; both hold the rate constant inside each 5 min step. The HMS-equivalent is that same
excess through S13's SCS unit hydrograph, on the same 5 min basis.
"""

from __future__ import annotations

import json
import sys

import numpy as np

import case

sys.path.insert(0, str(case.BLOCK2_SCRIPTS))
from common import HMS, SITES, hms_reference, storm  # noqa: E402
from lumped_ref import ENGINE, GRID, TIMES_H, run_at  # noqa: E402

from wadi2d.hms import load_basin  # noqa: E402
from wadi2d.hydrology.transforms import ScsUnitHydrograph, convolve  # noqa: E402


def main() -> None:
    area = SITES["Bidah 03"]
    result = run_at(area)
    water = result.water[case.SUBBASIN]
    element = load_basin(HMS / "Basin_1.basin").subbasins[case.SUBBASIN]
    excess = np.asarray(water.excess)
    rain = np.asarray(water.precipitation)
    n24 = int(24 * 60 / GRID.dt_minutes)
    if excess[n24:].sum() != 0.0:
        raise ValueError("excess after 24 h")
    uh = ScsUnitHydrograph(case.LAG_MIN).unit_hydrograph(case.AREA_KM2, GRID.dt_minutes)
    q = convolve(excess, uh, GRID.n_times)
    outflow = np.asarray(ENGINE.basin and result.outflow["Bidah 03"]) if hasattr(result, "outflow") else None
    s = storm(area)
    hms = hms_reference()["Bidah 03"]
    out = {
        "storm_depth_mm": s["depth_mm"],
        "storm_area_km2": area,
        "rain_after_arf_mm": float(rain.sum()),
        "arf": float(rain.sum() / s["depth_mm"]),
        "curve_number": float(element.loss.curve_number),
        "initial_abstraction_mm": float(element.loss.initial_abstraction),
        "lag_min": float(element.transform.lag),
        "excess_mm": float(excess.sum()),
        "excess_ratio": float(excess.sum() / rain.sum()),
        "first_excess_h": float((np.argmax(excess > 0.0)) * GRID.dt_minutes / 60.0),
        "peak_5min_mm": float(excess.max()),
        "peak_step_end_h": float((np.argmax(excess) + 1) * GRID.dt_minutes / 60.0),
        "hms_equiv_peak": float(q.max()),
        "hms_equiv_t_h": float(TIMES_H[int(np.argmax(q))]),
        "hms_equiv_volume_m3": float(np.trapezoid(q) * GRID.dt_seconds),
        "lumped_bidah_peak": None if outflow is None else float(outflow.max()),
        "hms_result_bidah": hms,
    }
    (case.HERE / "excess.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    np.savetxt(case.HERE / "excess_5min.csv", np.column_stack((np.arange(1, n24 + 1) * 5.0, excess[:n24])),
               delimiter=",", header="end_of_step_min,excess_mm", comments="", fmt="%.1f,%.9f")  # fmt: skip
    np.savetxt(case.HERE / "hms_equiv.csv", np.column_stack((TIMES_H * 3600.0, q)), delimiter=",",
               header="t_s,q_m3s", comments="", fmt="%.1f,%.6f")  # fmt: skip
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
