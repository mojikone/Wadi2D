"""His question, in numbers: how far is Muskingum from the project's own Muskingum-Cunge on Block 2?

Block 2's HMS project, Basin 3, its depth-area analyses as HMS runs them (each point under the storm of its own
drainage area). Every Muskingum-Cunge reach gets K, X and subreaches from the helper
(``wadi2d.hydrology.muskingum_proposal.at_reference_flow``) at its own 200-yr peak inflow, the peak the reach
carries in the run of the smallest analysis point below it. Then:

1. 200 yr: Muskingum against Muskingum-Cunge, peak and time to peak at the five dams and five junctions;
2. the same K and X at 2, 100 and 10,000 yr: the drift of fixed numbers as the flood changes size;
3. 200 yr again with X = 0.1, 0.2, 0.3 on every reach, and with K 30 % down and up (subreaches counted again);
4. 200 yr with K and X taken at half each reach's peak, the reference flow EM 1110-2-1417 suggests.

Reads the project, writes ``results/block2_study.json`` and ``results/block2_study.md``. CPU only.
Usage (repo root on PYTHONPATH): ``python block2_study.py``.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from wadi2d.basin.parameters import kirpich_travel_minutes
from wadi2d.config.schema import REACH_MUSKINGUM
from wadi2d.hms import load_nals, load_results
from wadi2d.hms.methods import MuskingumCungeRoute
from wadi2d.hydrology.depth_area import analyse_point
from wadi2d.hydrology.from_hms import basin_from_hms, grid_from_hms
from wadi2d.hydrology.model import Reach
from wadi2d.hydrology.muskingum import Muskingum, reach_notes
from wadi2d.hydrology.muskingum_proposal import at_index_celerity, at_reference_flow, at_travel_time
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.hydrology.replication import RESULTS_FOLDER, _point_storm, _Project, results_file_name

HERE = Path(__file__).resolve().parents[1]
PROJECT = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\HEC_HMS_Block_02\HEC_HMS_Block_02.hms")
BASIN = "Basin 3"
DESIGN = 200
PERIODS = (2, 100, 200, 10000)
DAMS = ("Z4C", "R2A", "Faydh 01", "Bidah 03", "R5A")
JUNCTIONS = ("J2", "J13", "RIJ-J2", "FIZ-J1", "FAY-J3")
POINTS = (*DAMS, *JUNCTIONS)
X_VALUES = (0.1, 0.2, 0.3)
K_FACTORS = (0.7, 1.3)
HALF = 0.5
ALONE = ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "RIJ-R1", "FIZ-R1", "FAY-R1", "HAT-R3", "HAT-R5")
"""The eight hill reaches, and five long channel reaches of the plain below the dams."""
LIMBS = ("R3", "R7", "HAT-R3")
LIMB_OFFSETS_MIN = (-90, -60, -30, -15, 0, 15, 30, 60, 90)
"""Where the two outflow hydrographs of a reach are read, minutes from the Muskingum-Cunge peak."""
TIMING_ROUTES = 200
DRY_REACH_M3S = 0.01
"""A reach whose 200-yr peak is under this carries no flood to take a reference flow from (HMS's own low-flow figure)."""


def analysis_name(period: int) -> str:
    return f"DA {period}yr B3"


class Study:
    def __init__(self) -> None:
        self.project = _Project(PROJECT)
        self.hms_basin, self.cunge = self.project.model(BASIN)
        self.basin_path = self.project.project.path_of(self.project.project.basins[BASIN])
        self.analyses = {a.name: a for a in load_nals(PROJECT.with_suffix(".nals")).analyses}
        self.step = grid_from_hms(self.analyses[analysis_name(DESIGN)]).dt_minutes
        self.sections = {
            name: element.route
            for name, element in self.hms_basin.reaches.items()
            if isinstance(element.route, MuskingumCungeRoute)
        }

    def storm_and_grid(self, period: int):
        analysis = self.analyses[analysis_name(period)]
        met = self.project.project.path_of(self.project.project.mets[analysis.met_model_name])
        storm = _point_storm(met, self.project.tables, self.hms_basin, self.cunge.basin, self.basin_path, PROJECT.stem)
        return storm, grid_from_hms(analysis)

    def at_points(self, engine: LumpedEngine, period: int, points=POINTS) -> dict[str, dict]:
        storm, grid = self.storm_and_grid(period)
        found = {}
        for point in points:
            result = analyse_point(engine, storm, grid, point)
            lowest = min(float(result.run.outflow[name].min()) for name in result.run.outflow)
            found[point] = {
                "peak_m3s": result.peak, "peak_h": result.peak_minutes / 60.0, "volume_m3": result.volume_m3,
                "lowest_outflow_m3s": lowest,
            }
        return found

    def reach_peaks(self, period: int) -> dict[str, dict]:
        """Each Muskingum-Cunge reach's peak inflow, in the run of the smallest analysis point below it."""
        storm, grid = self.storm_and_grid(period)
        basin = self.cunge.basin
        points = sorted(self.analyses[analysis_name(period)].points, key=basin.drainage_area)
        peaks: dict[str, dict] = {}
        for point in points:
            above = basin.upstream_of(point)
            wanted = [name for name in self.sections if name in above and name not in peaks]
            if not wanted:
                continue
            run = analyse_point(self.cunge, storm, grid, point).run
            for name in wanted:
                peaks[name] = {
                    "inflow_peak_m3s": float(run.inflow[name].max()), "point": point,
                    "outflow_peak_m3s": float(run.outflow[name].max()),
                    "inflow_peak_h": float(np.argmax(run.inflow[name])) * grid.dt_minutes / 60.0,
                    "outflow_peak_h": float(np.argmax(run.outflow[name])) * grid.dt_minutes / 60.0,
                }
        return peaks

    def proposals(self, flows: dict[str, float]) -> dict[str, dict]:
        """The helper at each reach's flow; a reach that carries nothing in the reference run (below a dam that
        does not spill) has no flood to read, and takes the helper's own fallback, the flow of its index celerity."""
        rows = {}
        for name, route in self.sections.items():
            section = (route.length, route.energy_slope, route.mannings_n, route.bottom_width, route.side_slope)
            if flows[name] >= DRY_REACH_M3S:
                found = at_reference_flow(*section, flows[name], self.step)
            else:
                found = at_index_celerity(*section, route.index_celerity, self.step)
            rows[name] = found.as_dict()
        return rows

    def muskingum(self, rows: dict[str, dict]) -> LumpedEngine:
        given = {
            name: SimpleNamespace(k_hours=row["k_hours"], x=row["x"], subreaches=row["subreaches"])
            for name, row in rows.items()
        }
        basin = basin_from_hms(self.hms_basin, self.project.tables, REACH_MUSKINGUM, muskingum=given)
        return LumpedEngine(basin)

    def hms_own(self, period: int) -> dict[str, dict]:
        """HMS's own peak and time at the points that are analysis points of the project, from its results file.
        J2 and J13 are not: there the comparison is this engine's two methods under the storm of the point's area."""
        results = load_results(PROJECT.parent / RESULTS_FOLDER / results_file_name(analysis_name(period)))
        found = {}
        for point in POINTS:
            if point not in results.points:
                continue
            element = results.element(point)
            hours = (element.outflow_max_time - results.start).total_seconds() / 3600.0
            found[point] = {"peak_m3s": element.outflow_max, "peak_h": hours}
        return found


def with_x(rows: dict[str, dict], x: float) -> dict[str, dict]:
    return {name: row | {"x": x} for name, row in rows.items()}


def with_k(rows: dict[str, dict], factor: float, step: float) -> dict[str, dict]:
    """K scaled, the subreaches counted again as K over the step; X as it was, cut to the stable ceiling if the
    count leaves it outside (it then says so in ``x_cut``)."""
    scaled = {}
    for name, row in rows.items():
        k = round(row["k_hours"] * factor, 4)
        count = max(1, math.floor(k * 60.0 / step + 0.5))
        ratio = step * count / (2.0 * k * 60.0)
        ceiling = min(0.5, ratio, 1.0 - ratio)
        x = row["x"] if ceiling < 0.0 or row["x"] <= ceiling else math.floor(ceiling * 1000.0) / 1000.0
        scaled[name] = row | {"k_hours": k, "subreaches": count, "x": x, "x_cut": x != row["x"]}
    return scaled


def differences(case: dict[str, dict], reference: dict[str, dict]) -> dict[str, dict]:
    return {
        point: {
            "peak_percent": 100.0 * (case[point]["peak_m3s"] / reference[point]["peak_m3s"] - 1.0),
            "time_min": 60.0 * (case[point]["peak_h"] - reference[point]["peak_h"]),
        }
        for point in reference
    }


def main() -> None:
    started = time.monotonic()
    study = Study()
    out: dict = {"project": PROJECT.name, "basin": BASIN, "step_minutes": study.step, "points": list(POINTS)}
    peaks = study.reach_peaks(DESIGN)
    out["reach_peaks_200yr"] = peaks
    rows = study.proposals({name: peak["inflow_peak_m3s"] for name, peak in peaks.items()})
    out["proposals_at_peak"] = rows
    engine = study.muskingum(rows)
    out["notes"] = reach_notes(engine.basin, study.step)
    out["unstable"] = sorted(name for name, row in rows.items() if not row["stable"])
    cunge, fixed = {}, {}
    for period in PERIODS:
        cunge[period] = study.at_points(study.cunge, period)
        fixed[period] = study.at_points(engine, period)
        print(f"{period} yr done, {time.monotonic() - started:.0f} s", flush=True)
    out["hms_own_200yr"] = study.hms_own(DESIGN)
    out["muskingum_cunge"] = {str(p): cunge[p] for p in PERIODS}
    out["muskingum_fixed"] = {str(p): fixed[p] for p in PERIODS}
    out["difference_fixed"] = {str(p): differences(fixed[p], cunge[p]) for p in PERIODS}
    reach_drift = {}
    for period in PERIODS:  # the reaches themselves, each Muskingum reach on the Muskingum-Cunge run's own inflow
        storm, grid = study.storm_and_grid(period)
        reach_drift[str(period)] = {}
        for name in ALONE:
            run = analyse_point(study.cunge, storm, grid, peaks[name]["point"]).run
            inflow, reference = run.inflow[name], run.outflow[name]
            method = engine.basin.elements[name].routing
            assert isinstance(engine.basin.elements[name], Reach) and isinstance(method, Muskingum)
            routed = method.route(inflow, grid.dt_minutes)
            seconds = grid.dt_minutes * 60.0
            if inflow.max() < DRY_REACH_M3S:  # below a dam that does not spill at this flood
                reach_drift[str(period)][name] = None
                continue
            if period == DESIGN and name in LIMBS:
                at = int(np.argmax(reference))
                out.setdefault("limbs_200yr", {})[name] = {
                    str(offset): {"cunge_m3s": float(reference[at + offset // 5]), "muskingum_m3s": float(routed[at + offset // 5])}
                    for offset in LIMB_OFFSETS_MIN
                }
            reach_drift[str(period)][name] = {
                "inflow_peak_m3s": float(inflow.max()),
                "cunge_peak_m3s": float(reference.max()), "muskingum_peak_m3s": float(routed.max()),
                "peak_percent": 100.0 * (float(routed.max()) / float(reference.max()) - 1.0),
                "cunge_lag_min": (int(np.argmax(reference)) - int(np.argmax(inflow))) * grid.dt_minutes,
                "muskingum_lag_min": (int(np.argmax(routed)) - int(np.argmax(inflow))) * grid.dt_minutes,
                "cunge_out_over_in": float(np.trapezoid(reference) / np.trapezoid(inflow)),
                "muskingum_out_over_in": float(np.trapezoid(routed) / np.trapezoid(inflow)),
                "muskingum_lowest_m3s": float(routed.min()),
                "inflow_volume_m3": float(np.trapezoid(inflow)) * seconds,
            }
    out["reaches_alone"] = reach_drift
    sensitivity = {}
    for x in X_VALUES:
        case = study.at_points(study.muskingum(with_x(rows, x)), DESIGN)
        sensitivity[f"X = {x:g}"] = differences(case, cunge[DESIGN])
    for factor in K_FACTORS:
        scaled = with_k(rows, factor, study.step)
        case = study.at_points(study.muskingum(scaled), DESIGN)
        sensitivity[f"K x {factor:g}"] = differences(case, cunge[DESIGN])
        out[f"x_cut_at_k_{factor:g}"] = sorted(name for name, row in scaled.items() if row["x_cut"])
    half = study.proposals({name: HALF * peak["inflow_peak_m3s"] for name, peak in peaks.items()})
    out["proposals_at_half_peak"] = half
    sensitivity["K, X at half the peak"] = differences(study.at_points(study.muskingum(half), DESIGN), cunge[DESIGN])
    # the helper with no section to read: Kirpich on each reach's length and slope, X the default
    blind = {
        name: at_travel_time(kirpich_travel_minutes(route.length, route.energy_slope), study.step, "Kirpich:").as_dict()
        for name, route in study.sections.items()
    }
    out["proposals_by_kirpich"] = blind
    sensitivity["K by Kirpich, X 0.2"] = differences(study.at_points(study.muskingum(blind), DESIGN), cunge[DESIGN])
    out["sensitivity_200yr"] = sensitivity
    out["seconds"] = time.monotonic() - started
    # the cost of the two methods on the longest reach, one route of the 48 h series
    storm, grid = study.storm_and_grid(DESIGN)
    inflow = analyse_point(study.cunge, storm, grid, peaks["R1"]["point"]).run.inflow["R1"]
    timing = {}
    for label, method in (("muskingum_cunge", study.cunge.basin.elements["R1"].routing), ("muskingum", engine.basin.elements["R1"].routing)):
        method.route(inflow, grid.dt_minutes)
        tick = time.perf_counter()
        for _ in range(TIMING_ROUTES):
            method.route(inflow, grid.dt_minutes)
        timing[label] = (time.perf_counter() - tick) / TIMING_ROUTES * 1.0e6
    out["microseconds_per_route_R1"] = timing
    results = HERE / "results"
    results.mkdir(exist_ok=True)
    (results / "block2_study.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"written, {out['seconds']:.0f} s")


if __name__ == "__main__":
    main()
