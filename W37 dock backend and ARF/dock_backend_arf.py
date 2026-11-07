"""W37 through the real dock on Bidah at 40 m: the engine choice, and the depth-area study with its table and its stop.

1. The new widgets and their refusals.
2. Study A: the HMS storm (Block 2's FM_100yr, its ARF FM table), every HMS subbasin rain-on-grid on the Bidah domain,
   storm areas 10, 20.971 and 30 km2, the engine left automatic, the composite map ticked on a constant 20.971 km2
   accumulation raster. The table is checked against each run's own series; the run at 20.971 km2 is the exact-area run
   that the interpolation between 10 and 30 is measured against.
3. Study C: the same, 10, 30 and 90 km2, stopped in its second run.
4. Study B: a basin generated from the DEM, one subbasin above a reach junction in 2D so a hand-back exists, a short
   design storm with the same ARF table, bracketing storm areas (the default), the CPU engine.
5. A plain run with the CPU engine.
"""

import csv
import json
import math
import re

import numpy as np
from osgeo import gdal

LINE_AREA = 20.971
"""Bidah 03's drainage area at its dam line, the c10 validation job's."""
LISTED_A = "10, 20.971, 30"
LISTED_C = "10, 30, 90"
DX = 40.0
THRESHOLD_KM2 = 2.0


def job_of(folder):
    return json.loads((folder / "job.json").read_text(encoding="utf-8"))


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "unnamed"


def series_max(path, column):
    """(peak of |column|, its time) of a series file, at the precision the file holds."""
    with path.open(newline="", encoding="utf-8") as f:
        rows = [(float(r["t_s"]), abs(float(r[column]))) for r in csv.DictReader(f)]
    t, q = max(rows, key=lambda row: row[1])
    return q, t


def run_events(h, study):
    """The study's ``run`` events; ``h.events`` also catches its ``output`` events of kind run."""
    return [e for e in h.events(study, "run") if e["ev"] == "run"]


def run_folders(h, study):
    """{area: folder} from the study's own run events."""
    return {e["area_km2"]: study / e["folder"] for e in run_events(h, study)}


def interp(areas, peaks, area):
    return math.exp(np.interp(math.log(area), np.log(areas), np.log(peaks)))


DEPTH = """
import json, sys
from pathlib import Path
from wadi2d.config.schema import RunConfig
from wadi2d.forcing import build_storm
cfg = RunConfig.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps({"depth_mm": build_storm(cfg).total_depth}))
"""


def engine(h, code, *args):
    """A few lines on the engine's own Python, as W20 does: QGIS must not import the engine."""
    import os
    import subprocess

    from wadi2d_qgis.protocol import clean_env

    done = subprocess.run(
        [str(h.VENV), "-c", code, *[str(a) for a in args]], capture_output=True, text=True, check=True,
        env=clean_env(dict(os.environ)),
    )  # fmt: skip
    return next(json.loads(s) for s in done.stdout.splitlines() if s.startswith("{"))


def constant_raster(path, extent, value, wkt, pixel=10.0):
    """Finer than the cells: the composite takes the largest pixel inside a cell, and a cell with none reads the
    smallest run."""
    columns = int((extent.width() + 4 * pixel) / pixel)
    rows = int((extent.height() + 4 * pixel) / pixel)
    ds = gdal.GetDriverByName("GTiff").Create(str(path), columns, rows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((extent.xMinimum() - 2 * pixel, pixel, 0.0, extent.yMaximum() + 2 * pixel, 0.0, -pixel))
    ds.SetProjection(wkt)
    ds.GetRasterBand(1).WriteArray(np.full((rows, columns), value, np.float32))
    ds = None
    return path


def read_band(path):
    ds = gdal.Open(str(path))
    data = ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    ds = None
    return data


def wait_study(dock, limit=1500):
    import time

    start = time.monotonic()

    def done():
        if time.monotonic() - start > limit:
            raise TimeoutError(f"no study end in {limit} s: {dock.study.message.text()}")
        return dock.study_run is None and dock.study.start_button.isEnabled()

    return done


def start_events(h, folders):
    return {area: h.events(folder, "start")[-1].get("backend") for area, folder in folders.items()}


def scenario(h):
    ground = h.Bidah()
    c10 = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    dam = json.loads((h.VALIDATION / "jobs" / "dam_Bidah03_100yr_20.json").read_text(encoding="utf-8"))
    bidah = next(line for line in c10["outputs"]["lines"] if line["name"] == "Bidah 03")
    axis = next(line for line in dam["outputs"]["lines"] if line["name"] == "axis")
    lines = h.add_vector(
        h.geojson("design", [h.line(bidah["coordinates"], name="Bidah 03", area=LINE_AREA), h.line(axis["coordinates"], name="axis", area=None)]),
        "design lines", ground.crs,
    )  # fmt: skip
    cn = h.add_raster(h.BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn")
    accumulation = h.add_raster(constant_raster(h.P / "acc_constant.tif", ground.domain.extent(), LINE_AREA, ground.crs.toWkt()), "acc")
    dock = yield from h.open_dock()
    panel, box, hy, storm = dock.panel, dock.study, dock.hydrology, dock.storm

    h.log("=== 1 the widgets")
    engines = [panel.backend.itemData(i) for i in range(panel.backend.count())]
    h.check("the engine choices are the schema's", engines == dock.schema.enum("run.backend"), engines)
    h.check("the engine starts automatic", panel.backend.currentData() == "auto", panel.backend.currentText())
    h.check("the study comes after Run", dock.sections.index(box) == dock.sections.index(panel) + 1)
    h.check("bracketing areas by default", box.spacing.currentData() == "bracket", box.spacing.currentText())
    h.check("the label says the rule", box.areas_label.text().startswith("Up to 6 runs"), box.areas_label.text())
    h.check("the composite map is off by default", not box.composite.isChecked() and not box.composite_box.isVisible())
    h.check("no per-point exact tick", not hasattr(box, "exact"))
    box.setCollapsed(False)
    h.set_rain_job(dock, ground, "refused", dx=DX, sim_hours=1.0, pixels=False)  # no CN: a run's rain is its excess
    dock.boundaries.layer.setLayer(ground.mixed)
    box.start_button.click()
    h.check("steady rain is refused", "design storm with an area reduction table" in box.message.text(), box.message.text())
    hy.folder.setFilePath(str(h.BLOCK / "HEC_HMS_Block_02"))
    yield lambda: hy.files["basin"].count() > 0
    hy.files["met"].setCurrentText("FM_100yr.met")
    storm.kind.setCurrentIndex(storm.kind.findData("hms"))
    for r in range(hy.table.rowCount()):
        hy.table.cellWidget(r, 1).setCurrentText("2d")
    dock.points.layer.setLayer(lines)
    dock.points.name.setField("name")
    box.start_button.click()
    h.check("a line without its area field is refused", "drainage area" in box.message.text(), box.message.text())
    dock.points.area.setField("area")
    box.spacing.setCurrentIndex(box.spacing.findData("listed"))
    box.listed.setText(LISTED_A)
    h.check("listed areas are counted", box.areas_label.text() == "3 runs, one per storm area: 10, 20.97 and 30 km2.", box.areas_label.text())
    box.composite.setChecked(True)
    box.accumulation.setLayer(accumulation)
    box.units.setCurrentIndex(box.units.findData("km2"))
    h.widget_shot("study_before", box)

    h.log("=== 2 study A: the HMS storm, automatic engine, three storm areas, composite map")
    panel.folder.setFilePath(str(h.RUNS / "bidah"))
    box.start_button.click()
    yield lambda: dock.study_run is not None
    h.check("Run is held while a study runs", not panel.run_button.isEnabled() and not box.start_button.isEnabled())
    yield lambda: "Run 1 of 3" in box.status.text()
    h.log(f"status: {box.status.text()}")
    h.check("the study says how many runs are left", "2 runs left after it" in box.status.text(), box.status.text())
    yield lambda: "Run 3 of 3" in box.status.text() or dock.study_run is None
    h.check("the last run says so", "the last run" in box.status.text() or dock.study_run is None, box.status.text())
    yield wait_study(dock)
    study = h.RUNS / "bidah_arf"
    h.log(f"dock says: {box.message.text()}")
    h.check("study A finished", box.message.text().startswith("Finished: 3 runs"), box.message.text())
    h.widget_shot("study_a_table", box)
    saved = json.loads((study / "study.json").read_text(encoding="utf-8"))
    job = job_of(study)
    h.check("the study job's areas and composite", job["arf"]["areas_km2"] == [10.0, 20.971, 30.0] and job["arf"]["accumulation_units"] == "km2", job["arf"])
    h.check("an automatic engine is not in the job", "backend" not in job["run"], job["run"])
    h.check("the HMS control file set 48 h", job["run"]["duration_s"] == 172800.0, job["run"]["duration_s"])
    folders = run_folders(h, study)
    backends = start_events(h, folders)
    h.check("one run per storm area", sorted(folders) == [10.0, 20.971, 30.0], sorted(folders))
    h.check("each run started on the GPU", set(backends.values()) == {"gpu"}, backends)
    rows = saved["table"]
    h.check("one row: the line with an area; axis has none", [r["design_point"] for r in rows] == ["Bidah 03"], [r["design_point"] for r in rows])
    h.check("the dock's table is the file's", box.table.rowCount() == 1 and box.table.item(0, 2).text() == f"{rows[0]['design_peak_m3s']:.1f}", box.table.item(0, 2).text() if box.table.rowCount() else None)
    h.check("the dock names the file", str(study / "design_points.csv") in box.file_label.text(), box.file_label.text())
    with (study / "design_points.csv").open(newline="", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    h.check("the csv holds the same row", float(csv_rows[0]["design_peak_m3s"]) == rows[0]["design_peak_m3s"], csv_rows[0]["design_peak_m3s"])
    peaks = {a: series_max(folder / "series" / "line_Bidah_03.csv", "discharge_m3s") for a, folder in folders.items()}
    h.log(f"line peaks by storm area: { {a: round(p[0], 3) for a, p in peaks.items()} }")
    row = rows[0]
    low, high = row["storm_area_low_km2"], row["storm_area_high_km2"]
    h.check("the row reads the runs either side", (low, high) == (10.0, 20.971), (low, high))
    h.check("its peaks are those runs' series peaks", abs(row["peak_low_m3s"] / peaks[low][0] - 1) < 1e-5 and abs(row["peak_high_m3s"] / peaks[high][0] - 1) < 1e-5, (row["peak_low_m3s"], peaks[low][0], row["peak_high_m3s"], peaks[high][0]))
    exact = peaks[LINE_AREA][0]
    h.check("at its own area the design peak is that run's", abs(row["design_peak_m3s"] / exact - 1) < 1e-5, (row["design_peak_m3s"], exact))
    between = interp([10.0, 30.0], [peaks[10.0][0], peaks[30.0][0]], LINE_AREA)
    h.log(f"INTERPOLATION Bidah 03 at {LINE_AREA} km2 from 10 and 30 km2: {between:.3f} against the exact-area run {exact:.3f} m3/s, {between / exact - 1:+.4%}")
    h.check("the interpolation between 10 and 30 is within 1 % of the exact run", abs(between / exact - 1) < 0.01, f"{between / exact - 1:+.4%}")
    table = job["storm"]["arf"]
    factor = {a: float(np.interp(a, table["areas_km2"], table["factors"])) for a in folders}
    depth = {a: engine(h, DEPTH, folder / "config.resolved.json")["depth_mm"] for a, folder in folders.items()}
    worst = max(abs(depth[a] / (job["storm"]["depth_mm"] * factor[a]) - 1) for a in folders)
    excess = {a: round(h.events(folder, "done")[-1]["balance"]["rain_m3"]) for a, folder in folders.items()}
    h.log(f"storm depth read by each run {depth} mm; ARF {factor}; net rain on the grid {excess} m3 (after the HMS losses)")
    h.check("each run read the storm at the ARF factor of its storm area", worst < 1e-9, f"{worst:.2e}")
    resolved = {a: json.loads((folder / "config.resolved.json").read_text(encoding="utf-8"))["storm"]["storm_area_km2"] for a, folder in folders.items()}
    h.check("each run's storm area is its own", all(abs(resolved[a] - a) < 1e-9 for a in folders), resolved)
    composite = study / "composite" / "max_depth.tif"
    h.check("the composite map was written", composite.is_file())
    if composite.is_file():
        diff = float(np.nanmax(np.abs(read_band(composite) - read_band(folders[LINE_AREA] / "maps" / "max_depth.tif"))))
        h.check("on a constant 20.971 km2 raster the composite is the 20.971 run", diff < 1e-5, diff)
    h.check("the composite is loaded as a group", h.group_of("bidah_arf composite") is not None)

    h.log("=== 3 study C: stopped in its second run")
    box.listed.setText(LISTED_C)
    box.composite.setChecked(False)
    box.start_button.click()
    yield lambda: dock.study_run is not None
    run = dock.study_run
    yield lambda: run.state.index == 2 and run.state.run is not None and run.state.run.t > 0.0
    h.log(f"status before the stop: {box.status.text()}")
    h.check("the second run says one is left", "Run 2 of 3, storm area 30 km2; 1 run left after it." in box.status.text(), box.status.text())
    box.stop_button.click()
    yield wait_study(dock, 300)
    stopped = h.RUNS / "bidah_arf_2"
    said = box.message.text()
    h.log(f"dock says: {said}")
    h.check("a stopped study says how far it got", said.startswith("Stopped after 1 of 3 runs") and "no design table" in said, said)
    done = h.events(stopped, "done")[-1]
    h.check("the engine stopped it", done["status"] == "stopped" and done["code"] == 6, done)
    h.check("no table, no stop file left", not (stopped / "design_points.csv").exists() and not (stopped / "stop").exists())
    h.check("the third run never started", len(run_events(h, stopped)) == 2, len(run_events(h, stopped)))
    second = h.events(run_folders(h, stopped)[30.0], "done")[-1]
    h.check("the run in progress stopped too", second["status"] == "stopped", second.get("status"))
    h.check("Start study is back, the table empty", box.start_button.isEnabled() and box.table.rowCount() == 0)

    h.log("=== 4 study B: generated basin, a hand-back, bracketing areas, the CPU engine")
    imported = json.loads((study / "hms_import.json").read_text(encoding="utf-8"))["storm"]
    hy.folder.setFilePath("")
    storm.kind.setCurrentIndex(storm.kind.findData("hypothetical"))
    storm.design_depth.setValue(100.0)
    storm.design_hours.setValue(2.0)
    storm.pattern.set_rows(list(zip(imported["time_percent"], imported["depth_percent"], strict=True)))
    storm.storm_area.setValue(LINE_AREA)
    storm.arf.set_rows(list(zip(imported["arf"]["areas_km2"], imported["arf"]["factors"], strict=True)))
    panel.duration.setValue(4.0)
    panel.folder.setFilePath(str(h.RUNS / "basin"))
    hy.cn.raster.setLayer(cn)
    basin = hy.basin
    basin.setChecked(True)
    basin.threshold.setValue(THRESHOLD_KM2)
    basin.generate_button.click()
    yield lambda: basin.generate_button.isEnabled() and basin.model is not None
    model = basin.model
    h.log(f"basin: {basin.summary.text()}")
    routes = {r["junction"]: r for r in model["routes"]}
    reach_junction = next(j for j, r in routes.items() if r["route"] == "reach")
    above = next(e["name"] for e in model["elements"] if e["kind"] == "subbasin" and e["downstream"] == reach_junction)
    for r in range(hy.table.rowCount()):
        if hy.table.item(r, 0).text() == above:
            hy.table.cellWidget(r, 1).setCurrentText("2d")
    h.log(f"{above} in 2D above {reach_junction}")
    panel.backend.setCurrentIndex(panel.backend.findData("cpu"))
    box.spacing.setCurrentIndex(box.spacing.findData("bracket"))
    box.start_button.click()
    yield lambda: dock.study_run is not None
    yield wait_study(dock, 1800)
    study_b = h.RUNS / "basin_arf"
    said = box.message.text()
    h.log(f"dock says: {said}")
    h.check("study B finished", said.startswith("Finished:"), said)
    h.widget_shot("study_b_table", box)
    job = job_of(study_b)
    h.check("the CPU choice is in the job", job["run"].get("backend") == "cpu", job["run"])
    h.check("bracketing areas asked", job["arf"] == {"bracket": True}, job["arf"])
    own = {
        e["area_km2"]: json.loads((study_b / e["folder"] / "config.resolved.json").read_text(encoding="utf-8"))["storm"]["storm_area_km2"]
        for e in run_events(h, study_b)
    }  # fmt: skip
    h.check("each run of B read the storm at its own area", all(abs(v - a) < 1e-9 for a, v in own.items()), own)
    start = h.events(study_b, "start")[-1]
    areas = start["areas_km2"]
    folders = run_folders(h, study_b)
    backends = start_events(h, folders)
    h.check("each run started on the CPU", set(backends.values()) == {"cpu"}, backends)
    h.check("one 2D run per storm area", len(folders) == len(areas) == len(list((study_b / "runs").iterdir())), (len(folders), areas))
    saved = json.loads((study_b / "study.json").read_text(encoding="utf-8"))
    rows = saved["table"]
    kinds = {}
    for row in rows:
        kinds.setdefault(row["read_as"], []).append(row["design_point"])
    h.log(f"storm areas {areas}; elements {start.get('elements')}; rows by kind {kinds}; on the grid {saved['on_grid']}")
    fed = [r for r in rows if r["read_as"].startswith("lumped element with 2D water")]
    lumped = [r for r in rows if r["read_as"].startswith("lumped element, rerun")]
    wanted = [LINE_AREA] + [r["drainage_area_km2"] for r in fed]
    h.check("the areas span the line and the fed elements", abs(areas[0] - min(wanted)) < 1e-3 and abs(areas[-1] - max(wanted)) < 1e-3, (areas, wanted))
    ratios = [b / a for a, b in zip(areas, areas[1:])]
    h.check("at most 6, neighbours at most 2 x apart", len(areas) <= 6 and (len(areas) == 6 or all(r <= 2.0 + 1e-9 for r in ratios)), ratios)
    h.check("rows for the line, fed elements and lumped elements", rows[0]["design_point"] == "Bidah 03" and fed and lumped, sorted(kinds))
    grid_a = np.array(sorted(folders))
    worst_fed = 0.0
    for r in fed:
        found = {a: series_max(folders[a] / "series" / f"network_{safe(r['design_point'])}.csv", "outflow_m3s")[0] for a in folders}
        ok = abs(r["peak_low_m3s"] - found[r["storm_area_low_km2"]]) <= 1e-5 * max(found[r["storm_area_low_km2"]], 1.0)
        ok &= abs(r["peak_high_m3s"] - found[r["storm_area_high_km2"]]) <= 1e-5 * max(found[r["storm_area_high_km2"]], 1.0)
        worst_fed = max(worst_fed, 0.0 if ok else 1.0)
    h.check("each fed element's peaks are its network series in the runs either side", worst_fed == 0.0, [r["design_point"] for r in fed])
    h.check("each lumped element reads its own area, no interpolation", all(r["storm_area_low_km2"] == r["storm_area_high_km2"] == r["drainage_area_km2"] for r in lumped))
    errors = {}
    for r in lumped:
        own = [series_max(folders[a] / "series" / f"network_{safe(r['design_point'])}.csv", "outflow_m3s")[0] for a in grid_a]
        if min(own) > 0.0 and len(grid_a) > 1:
            errors[r["design_point"]] = interp(grid_a, own, r["drainage_area_km2"]) / r["design_peak_m3s"] - 1.0
    h.log(f"INTERPOLATION lumped elements, the 2D runs' network series interpolated to each element's area against its exact rerun: { {k: f'{v:+.3%}' for k, v in errors.items()} }")
    if saved["on_grid"]:
        h.check("the dock names the elements on the grid", all(n in box.file_label.text() for n in saved["on_grid"]), box.file_label.text())

    h.log("=== 5 a plain run on the CPU")
    panel.folder.setFilePath(str(h.RUNS / "plain_cpu"))
    yield from h.run(dock, 900)
    plain = h.RUNS / "plain_cpu"
    h.check("the plain run finished", h.events(plain, "done")[-1].get("code") == 0, panel.message.text())
    h.check("its job says cpu and carries no study", job_of(plain)["run"].get("backend") == "cpu" and "arf" not in job_of(plain), job_of(plain)["run"])
    h.check("its engine started on the CPU", h.events(plain, "start")[-1].get("backend") == "cpu", h.events(plain, "start")[-1].get("backend"))
    panel.backend.setCurrentIndex(panel.backend.findData("auto"))
