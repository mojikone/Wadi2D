"""Bidah 03 from the HMS project, two ways. Venv python only. usage: hms_reference.py OUT.json

1. HMS's own numbers, read from the project's output DSS files: the depth-area analyses `DA 200yr B1` and `DA PMP B1`
   at the point Bidah 03 (storm area = the point's own 20.971 km2, ARF FM there), and the met records of the FM runs.
   The FM run files hold precipitation only, no flow.
2. HMS's method for S13 (SCS CN 87.6, Ia 7.2 mm, SCS lag 53.3 min) recomputed by Wadi2D's lumped engine, which
   replicates HMS to 0.002 % (W1): the 251 mm point depth with no ARF, the same with HMS's ARF at 20.971 km2 to show the
   recomputation meets HMS's own result, and the RP200 grids' own rain over the S13 polygon (area-weighted), no ARF.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pyogrio
import shapely

from wadi2d.hms import load_basin, load_met, load_pdata
from wadi2d.hms.dss import daa_fpart, met_fpart, open_dss
from wadi2d.hydrology.from_hms import basin_from_hms, load_project_tables, storm_from_hms
from wadi2d.hydrology.model import TimeGrid
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.io.rain import read_rain
from wadi2d.storm.gridded import GriddedStorm
from wadi2d.storm.hypothetical import HypotheticalStorm
from wadi2d.storm.rain_frames import RainSpec

HMS = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02")
GRID = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Grid")
FILES = {
    "nc": GRID / "netCDF" / "Precipitation_RP200_10min.nc",
    "dss": GRID / "DSS" / "Precipitation_RP200_10min.dss",
}
POINT, SUB = "Bidah 03", "S13"
STEP_MIN, HOURS = 5.0, 48.0
UTM = "EPSG:32640"


def hydrograph(t_min: np.ndarray, q: np.ndarray) -> dict:
    k = int(np.argmax(q))
    volume = float(np.sum(0.5 * (q[1:] + q[:-1]) * np.diff(t_min) * 60.0))
    return {"peak_m3s": float(q[k]), "peak_h": float(t_min[k] / 60.0), "volume_m3": volume}


def hms_own(analysis: str, file: str, met: str) -> dict:
    with open_dss(HMS / file) as dss:
        flow = dss.read_timeseries(POINT, "FLOW", daa_fpart(analysis, POINT))
        excess = dss.read_timeseries(SUB, "PRECIP-EXCESS-CUM", daa_fpart(analysis, POINT))
        loss = dss.read_timeseries(SUB, "PRECIP-LOSS-CUM", daa_fpart(analysis, POINT))
    t0 = np.datetime64("2000-01-01T00:00:00")
    t = (flow.times - t0).astype("timedelta64[s]").astype(float) / 60.0
    out = hydrograph(t, flow.values)
    out.update(
        file=file, record=str(flow.pathname), units=flow.units, s13_excess_mm=float(np.nanmax(excess.values)),
        s13_precip_mm=float(np.nanmax(excess.values) + np.nanmax(loss.values)),
    )  # fmt: skip
    with open_dss(HMS / met) as dss:
        met_rain = dss.read_timeseries(SUB, "PRECIP-CUM", met_fpart(Path(met).stem.replace("_", " "), POINT))
    out["met_record"] = str(met_rain.pathname)
    out["met_s13_precip_mm"] = float(np.nanmax(met_rain.values))
    return out


def main(argv: list[str]) -> int:
    out = Path(argv[0])
    hms_basin = load_basin(HMS / "Basin_1.basin")
    basin = basin_from_hms(hms_basin)
    engine = LumpedEngine(basin)
    grid = TimeGrid(STEP_MIN, int(HOURS * 60 / STEP_MIN))
    tables = load_project_tables(load_pdata(HMS / "HEC_HMS_Block_02.pdata"), HMS / "HEC_HMS_Block_02.dss")
    storm = storm_from_hms(load_met(HMS / "FM_200yr.met").storm, tables)
    frame = pyogrio.read_dataframe(HMS / "Basin_1.sqlite", layer="subbasin2d")
    polygon = shapely.make_valid(frame.loc[frame["name"] == SUB].geometry.iloc[0])

    def at_point(rain) -> dict:
        run = engine.run(rain, grid, only=[SUB, POINT])
        result = hydrograph(grid.minutes, run.outflow[POINT])
        result["s13_precip_mm"] = float(run.water[SUB].precipitation.sum())
        result["s13_excess_mm"] = float(run.water[SUB].excess.sum())
        return result

    report = {
        "met_FM_200yr": {
            "depth_mm": storm.depth_mm,
            "duration_h": storm.duration_hours,
            "storm_area_km2": storm.storm_area_km2,
            "arf_at_storm_area": storm.area_factor,
        },
        "hms_own_DA_200yr": hms_own("DA 200yr B1", "DA_200yr_B1.dss", "FM_200yr.dss"),
        "hms_own_DA_PMP": hms_own("DA PMP B1", "DA_PMP_B1.dss", "FM_PMP.dss"),
        "replica_251mm_no_arf": at_point(
            HypotheticalStorm(storm.depth_mm, storm.pattern, storm.duration_hours)
        ),
        "replica_251mm_arf_at_20.971": at_point(storm.at_area(20.971)),
    }
    for key, path in FILES.items():
        frames = read_rain(path, RainSpec(None, "auto", None, "end"))
        rain = GriddedStorm(frames).bind({SUB: polygon}, UTM)
        report[f"replica_grid_{key}_no_arf"] = at_point(rain)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
