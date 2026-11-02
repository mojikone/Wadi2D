"""The forcing of both models: the 100-yr Block 2 storm at Faydh 01's storm area, S11 and S12 SCS losses, area-weighted.

RAS's table is one depth per step for the whole mesh, so the excess is uniform: the area-weighted mean of S11 and S12.
HMS keeps them apart. The reference hydrograph is HMS's own at the site through the lumped engine, which replicates it.
"""

from __future__ import annotations

import json
import sys

import numpy as np

import case

sys.path.insert(0, str(case.BLOCK2_SCRIPTS))
from common import HMS, SITES, hms_reference, polygons, storm  # noqa: E402
from lumped_ref import GRID, TIMES_H, run_at  # noqa: E402


def main() -> None:
    area = SITES[case.SITE]
    r = run_at(area)
    p = polygons()
    a = {n: p[n].area / 1e6 for n in case.SUBBASINS}
    water = {n: r.water[n] for n in case.SUBBASINS}
    ex = {n: np.asarray(water[n].excess) for n in case.SUBBASINS}
    total = sum(a.values())
    mean = sum(ex[n] * a[n] for n in case.SUBBASINS) / total
    n24 = int(24 * 60 / GRID.dt_minutes)
    if mean[n24:].sum() != 0.0:
        raise ValueError("excess after 24 h")
    q = np.asarray(r.outflow[case.SITE])
    out = {
        "storm": storm(area)["depth_mm"],
        "storm_area_km2": area,
        "areas_km2": a,
        "excess_mm_by_subbasin": {n: float(ex[n].sum()) for n in case.SUBBASINS},
        "rain_mm_by_subbasin": {n: float(np.asarray(water[n].precipitation).sum()) for n in case.SUBBASINS},
        "excess_mm": float(mean.sum()),
        "first_excess_h": float(np.argmax(mean > 0.0) * GRID.dt_minutes / 60.0),
        "peak_5min_mm": float(mean.max()),
        "peak_step_end_h": float((np.argmax(mean) + 1) * GRID.dt_minutes / 60.0),
        "lumped_peak": float(q.max()),
        "lumped_t_h": float(TIMES_H[int(np.argmax(q))]),
        "lumped_volume_m3": float(np.trapezoid(q) * GRID.dt_seconds),
        "hms_result": hms_reference()[case.SITE],
    }
    (case.HERE / "excess.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    np.savetxt(case.HERE / "excess_5min.csv", np.column_stack((np.arange(1, n24 + 1) * 5.0, mean[:n24])),
               delimiter=",", header="end_of_step_min,excess_mm", comments="", fmt="%.1f,%.9f")  # fmt: skip
    np.savetxt(case.HERE / "hms_equiv.csv", np.column_stack((TIMES_H * 3600.0, q)), delimiter=",",
               header="t_s,q_m3s", comments="", fmt="%.1f,%.6f")  # fmt: skip
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
