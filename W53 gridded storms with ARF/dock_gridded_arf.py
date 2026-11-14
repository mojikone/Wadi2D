"""W53 through the real dock on Bidah 03 at 30 m: the owner's RP100 NetCDF grid with and without its area reduction,
the HMS project's table taken when the dock's is left empty, and a depth-area study on the gridded storm.

usage: tests/dock/run_check.ps1 "<this file>" "<throwaway folder inside the worktree>"

The rules were fixed before the runs and are the constants below. Runs on a CN 100 raster show the gross rain, which is
what the factor multiplies; runs on the project's CN grid give the design peaks.
"""

import csv
import json
import math
from pathlib import Path

import numpy as np

DX = 30.0
HOURS = 30.0
LINE = "Bidah 03"
S13_KM2 = 20.971
RAIN = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Grid\netCDF\Precipitation_RP100_10min.nc")
ARF_FM = [  # the HMS project's ARF FM table, typed into the dock as a user would
    (1.0, 0.999), (5.0, 0.994), (10.0, 0.987), (20.0, 0.976), (30.0, 0.965), (40.0, 0.956), (50.0, 0.948),
    (100.0, 0.913), (200.0, 0.864), (500.0, 0.776), (1000.0, 0.694), (2000.0, 0.606),
]  # fmt: skip
STUDY_AREAS = "10, 20.971, 30"
ACCUMULATION = Path(__file__).resolve().parents[1] / "_throwaway_w53" / "study_lines" / "accumulation_km2.tif"
"""D8 catchment area in km2 on 30 m pixels over the Bidah 03 domain, made by study_lines_bidah.py."""
TRIBUTARY = [[438778.9, 2727391.1], [438991.1, 2727178.9]]
"""A 300 m line across a wadi draining 10.5 to 19.5 km2 on that raster: between the 10 and 20.971 km2 runs."""
FACTOR = 1e-9
"""The factor a run reports against the table read by hand at its storm area."""
GROSS = 1e-6
"""A run's gross rain with the reduction against factor x the run without it (CN 100)."""
MASS = 1e-6
"""Relative mass error of every run."""
SAME = 1e-9
"""The study's run at S13's own area against the single run at that area."""
PEAK_READ = 1e-5
"""The study's design peak against that run's line series as written."""
HERE = Path(__file__).resolve().parent
VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")
CN100 = """
import sys, json, numpy as np, rasterio
from rasterio.transform import from_origin
west, south, east, north = [float(v) for v in sys.argv[2:6]]
w, hgt = int((east - west) / 100) + 1, int((north - south) / 100) + 1
with rasterio.open(sys.argv[1], "w", driver="GTiff", height=hgt, width=w, count=1, dtype="float32", crs="EPSG:32640",
                   transform=from_origin(west, north, 100.0, 100.0)) as d:
    d.write(np.full((hgt, w), 100.0, np.float32), 1)
print(json.dumps({"ok": True}))
"""


def table_factor(area):
    areas, factors = zip(*ARF_FM, strict=True)
    return 1.0 if area < areas[0] else float(np.interp(area, areas, factors))


def venv(h, *args):
    import os
    import subprocess
    import sys

    if str(h.REPO / "plugin") not in sys.path:
        sys.path.insert(0, str(h.REPO / "plugin"))
    from wadi2d_qgis.protocol import clean_env

    env = clean_env(dict(os.environ))
    env["PYTHONPATH"] = str(h.REPO)
    done = subprocess.run([str(h.VENV), *[str(a) for a in args]], capture_output=True, text=True, env=env)
    if done.returncode:
        raise RuntimeError(done.stderr[-3000:])
    return json.loads(next(s for s in reversed(done.stdout.splitlines()) if s.startswith("{")))


def hydrograph(path, column="discharge_m3s"):
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    t = np.array([float(r["t_s"]) for r in rows])
    q = np.abs(np.array([float(r[column]) for r in rows]))
    k = int(np.argmax(q))
    return {"peak_m3s": float(q[k]), "peak_h": float(t[k] / 3600.0), "volume_m3": float(np.trapezoid(q, t))}


def ratio(a, b):
    return a / b - 1.0 if b else float("inf")


def click(canvas, tool, x, y, button):
    from qgis.gui import QgsMapMouseEvent
    from qgis.PyQt.QtCore import QEvent, QPoint

    pixel = canvas.getCoordinateTransform().transform(x, y)
    point = QPoint(round(pixel.x()), round(pixel.y()))
    tool.canvasReleaseEvent(QgsMapMouseEvent(canvas, QEvent.MouseButtonRelease, point, button))


def draw(lines, coordinates):
    """Through the real map tool, as clicks on the canvas (W21's way)."""
    from qgis.PyQt.QtCore import Qt

    lines.draw_button.click()
    canvas = lines.canvas
    tool = canvas.mapTool()
    assert tool is lines.tool
    for x, y in coordinates:
        click(canvas, tool, x, y, Qt.LeftButton)
    click(canvas, tool, *coordinates[-1], Qt.RightButton)


def wait_study(dock, limit=1800):
    import time

    start = time.monotonic()

    def done():
        if time.monotonic() - start > limit:
            raise TimeoutError(f"no study end in {limit} s: {dock.study.message.text()}")
        return dock.study_run is None and dock.study.start_button.isEnabled()

    return done


def scenario(h):
    h.TOTAL_LIMIT = 7200.0
    h.STEP_LIMIT = 2400.0
    if not h.VENV.is_file():  # a worktree has no venv of its own; the project's runs this checkout's code
        h.VENV = VENV
    ground = h.Bidah()
    record = {"runs": {}}
    lines = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))["outputs"]["lines"]
    coordinates = next(k["coordinates"] for k in lines if k["name"] == LINE)
    line = h.add_vector(h.geojson("bidah_line", [h.line(coordinates, name=LINE, area=S13_KM2)]), "Bidah 03 line", ground.crs)
    cn = h.add_raster(h.BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn")
    box_ = ground.domain.extent()
    cn100_path = h.DATA / "cn100.tif"
    venv(h, "-c", CN100, cn100_path, box_.xMinimum() - 1000, box_.yMinimum() - 1000, box_.xMaximum() + 1000,
         box_.yMaximum() + 1000)  # fmt: skip
    cn100 = h.add_raster(cn100_path, "cn 100")
    dock = yield from h.open_dock()
    hy, storm, study = dock.hydrology, dock.storm, dock.study

    h.log("=== 0 the widgets")
    storm.kind.setCurrentIndex(storm.kind.findData("gridded"))
    h.check("Reduce by area is off by default", not storm.grid_arf_on.isChecked())
    h.check("its area and table are hidden while it is off", not storm.grid_reduction.isVisibleTo(storm))
    h.check("its label says what it is for", "point depths" in storm.grid_arf_on.text(), storm.grid_arf_on.text())

    h.set_rain_job(dock, ground, "plain_cn", dx=DX, rain=10.0, hours=1.0, sim_hours=HOURS, pixels=False)
    dock.points.layer.setLayer(line)
    dock.points.name.setField("name")
    dock.points.area.setField("area")
    storm.kind.setCurrentIndex(storm.kind.findData("gridded"))
    storm.is_folder.setCurrentIndex(0)
    storm.rain_file.setFilePath(str(RAIN))
    yield lambda: storm.rain_label.text() and "Reading" not in storm.rain_label.text()
    h.log(f"rain label: {storm.rain_label.text()}")
    h.check("the dock reads 144 frames of 10 min", storm.rain_label.text().startswith("144 frames of 10 min"))

    def reduction(on, rows=ARF_FM, area=S13_KM2):
        storm.grid_arf_on.setChecked(on)
        storm.grid_area.setValue(area)
        storm.grid_arf.set_rows(rows)

    def run_one(name, cn_layer):
        hy.cn.raster.setLayer(cn_layer)
        dock.panel.folder.setFilePath(str(h.RUNS / name))
        yield from h.run(dock, 1500)
        out = h.RUNS / name
        done = h.events(out, "done")
        ok = bool(done) and done[-1].get("code") == 0
        h.check(f"{name}: the run finished", ok, dock.panel.message.text()[:300])
        entry = {"finished": ok}
        if ok:
            b = done[-1]["balance"]
            job = json.loads((out / "job.json").read_text(encoding="utf-8"))
            said = [e for e in h.events(out, "output") if e.get("kind") == "area_reduction"]
            entry.update(
                balance=b, line=hydrograph(out / "series" / "line_Bidah_03.csv"), job_storm=job["storm"],
                area_reduction=said, warnings=[e["message"] for e in h.events(out, "warn")],
            )  # fmt: skip
            h.check(f"{name}: mass error under {MASS:g}", abs(b["relative_error"]) < MASS, b["relative_error"])
            h.log(f"{name}: line {entry['line']}, rain {b['rain_m3']:.1f} m3, reduction {said}")
            for w in entry["warnings"]:
                h.log(f"  warn: {w[:300]}")
        record["runs"][name] = entry
        (h.P / "w53_dock.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        return entry

    h.log("=== 1 the grid as it is, then reduced at S13's area; the gross rain on CN 100, the design peak on the CN grid")
    want = table_factor(S13_KM2)
    for cn_name, cn_layer in (("gross", cn100), ("cn", cn)):
        reduction(False)
        plain = yield from run_one(f"{cn_name}_plain", cn_layer)
        if plain.get("finished"):
            js = plain["job_storm"]
            h.check(f"{cn_name}_plain: unticked, the job carries no reduction", "arf" not in js and "storm_area_km2" not in js, js)
            h.check(f"{cn_name}_plain: no factor is reported", not plain["area_reduction"])
        reduction(True)
        h.widget_shot(f"storm_reduced_{cn_name}", storm)
        reduced = yield from run_one(f"{cn_name}_arf", cn_layer)
        if reduced.get("finished"):
            js = reduced["job_storm"]
            h.check(
                f"{cn_name}_arf: the job carries the area and the typed table",
                js.get("storm_area_km2") == S13_KM2 and js.get("arf", {}).get("factors") == [f for _a, f in ARF_FM], js,
            )
            got = reduced["area_reduction"][0]["factor"] if reduced["area_reduction"] else float("nan")
            h.check(f"{cn_name}_arf: the factor reported is the table's at {S13_KM2} km2", abs(got - want) < FACTOR, f"{got} against {want}")
            h.check(f"{cn_name}_arf: the dock shows the factor in words", any(f"{want:.4f}" in w for w in reduced["warnings"]), reduced["warnings"])
        if plain.get("finished") and reduced.get("finished") and cn_name == "gross":
            r = reduced["balance"]["rain_m3"] / plain["balance"]["rain_m3"]
            h.check(f"gross: the rain is the factor times the grid within {GROSS:g}", abs(r / want - 1.0) < GROSS, f"{r:.9f} against {want:.9f}")

    h.log("=== 2 the HMS project loaded, the table left empty: the job takes the project's ARF FM")
    hy.folder.setFilePath(str(h.BLOCK / "HEC_HMS_Block_02"))
    yield lambda: hy.files["basin"].count() > 0
    hy.files["met"].setCurrentText("FM_100yr.met")
    storm.kind.setCurrentIndex(storm.kind.findData("gridded"))
    for r in range(hy.table.rowCount()):
        hy.table.cellWidget(r, 1).setCurrentText("2d")
    reduction(True, rows=[])
    h.check("the dock says an empty table takes the HMS project's", storm.grid_hms_note.isVisibleTo(storm), storm.grid_hms_note.text())
    h.widget_shot("storm_hms_table", storm)
    hms_run = yield from run_one("hms_table", cn)
    if hms_run.get("finished"):
        js = hms_run["job_storm"]
        h.check("hms_table: the job's table is ARF FM", js.get("arf", {}).get("areas_km2") == [a for a, _f in ARF_FM]
                and js["arf"]["factors"] == [f for _a, f in ARF_FM] and js["arf"].get("reduces_below_table") is False, js.get("arf"))  # fmt: skip
        got = hms_run["area_reduction"][0]["factor"] if hms_run["area_reduction"] else float("nan")
        h.check("hms_table: the same factor", abs(got - want) < FACTOR, got)
        h.check("hms_table: the HMS control file set 48 h", json.loads((h.RUNS / "hms_table" / "job.json").read_text(encoding="utf-8"))["run"]["duration_s"] == 172800.0)
    hy.folder.setFilePath("")

    h.log("=== 3 a depth-area study on the gridded storm, its own table, three storm areas")
    storm.kind.setCurrentIndex(storm.kind.findData("gridded"))
    reduction(True)
    hy.cn.raster.setLayer(cn)
    study.setCollapsed(False)
    study.spacing.setCurrentIndex(study.spacing.findData("arf_step"))
    h.check("the ARF-step rule is offered, 0.05 by default", study.spacing.currentData() == "arf_step" and abs(study.arf_step.value() - 0.05) < 1e-9, study.arf_step.value())
    study._refresh_areas()
    h.log(f"ARF-step label: {study.areas_label.text()}")
    h.check("the dock counts the ARF-step runs before the study", study.areas_label.text().startswith("1 run, one per storm area: 20.97 km2;"), study.areas_label.text())
    study.spacing.setCurrentIndex(study.spacing.findData("listed"))
    study.listed.setText(STUDY_AREAS)
    accumulation = h.add_raster(ACCUMULATION, "accumulation km2")
    study.accumulation.setLayer(accumulation)
    study.units.setCurrentIndex(study.units.findData("km2"))
    h.check("the flow accumulation row shows with the composite map off", study.accumulation_box.isVisibleTo(study) and not study.composite.isChecked())
    dock.panel.folder.setFilePath(str(h.RUNS / "grid"))
    study.start_button.click()
    yield lambda: dock.study_run is not None or bool(study.message.text())
    yield wait_study(dock)
    folder = h.RUNS / "grid_arf"
    said = study.message.text()
    h.log(f"study says: {said}")
    h.widget_shot("study_table", study)
    h.check("the study finished", said.startswith("Finished: 3 runs"), said)
    if (folder / "study.json").is_file():
        saved = json.loads((folder / "study.json").read_text(encoding="utf-8"))
        runs = {e["area_km2"]: folder / e["folder"] for e in h.events(folder, "run") if e["ev"] == "run"}
        factors = {}
        for area, run in runs.items():
            found = [e for e in h.events(run, "output") if e.get("kind") == "area_reduction"]
            factors[area] = found[0]["factor"] if found else float("nan")
        h.log(f"study factors: {factors}")
        h.check("each study run is reduced at its own storm area", all(abs(f - table_factor(a)) < FACTOR for a, f in factors.items()) and len(factors) == 3, factors)
        row = next(r for r in saved["table"] if r["design_point"] == LINE)
        record["study"] = {"row": row, "factors": factors}
        own = hydrograph(runs[S13_KM2] / "series" / "line_Bidah_03.csv")["peak_m3s"]
        single = record["runs"].get("cn_arf", {}).get("line", {}).get("peak_m3s", float("nan"))
        h.check("the study's run at 20.971 km2 is the single reduced run", abs(ratio(own, single)) < SAME, f"{own} against {single}")
        h.check("the design peak is that run's", abs(ratio(row["design_peak_m3s"], own)) < PEAK_READ, f"{row['design_peak_m3s']} against {own}")
        low = hydrograph(runs[10.0] / "series" / "line_Bidah_03.csv")["peak_m3s"]
        high = hydrograph(runs[30.0] / "series" / "line_Bidah_03.csv")["peak_m3s"]
        h.check("a smaller storm area gives the larger peak", low > own > high, (low, own, high))
        h.log(f"study row: {row}; log-area check {math.exp(np.interp(math.log(S13_KM2), np.log([10.0, 30.0]), np.log([low, high]))):.2f}")
        job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        h.check("the raster is in the study job, the composite map off", job["arf"].get("accumulation") and job["arf"].get("composite") is False and not (folder / "composite").exists(), job["arf"])

    h.log("=== 4 lines after the study: a tributary drawn on the map, the design line from the list")
    h.check("the study offers its result lines", study.lines_button.isVisibleTo(study))
    study.lines_button.click()
    lines = dock.line_panel
    yield lambda: lines.query is None and lines.items
    h.log(f"panel says: {lines.message.text()}")
    h.check("the panel says it is a study and how its lines read", lines.message.text().startswith("A depth-area study, runs at 10, 20.97, 30 km2.") and "flow accumulation raster" in lines.message.text(), lines.message.text())
    h.check("the design line is listed as such", lines.choice.itemText(0) == f"Design line: {LINE}", lines.choice.itemText(0))
    yield lambda: lines.query is None and not lines.waiting and lines.plot.view is not None
    design_view = lines.plot.view
    h.log(f"design line note: {design_view.note}")
    h.check("the design line reads its own area, the 20.971 km2 run", "20.97 km2 (its design line's)" in design_view.note, design_view.note)
    import time

    from qgis.core import QgsRectangle
    from qgis.utils import iface

    xs, ys = [p[0] for p in TRIBUTARY], [p[1] for p in TRIBUTARY]
    iface.mapCanvas().setExtent(QgsRectangle(min(xs) - 400.0, min(ys) - 400.0, max(xs) + 400.0, max(ys) + 400.0))
    iface.mapCanvas().refresh()
    pixel = iface.mapCanvas().mapUnitsPerPixel()
    started = time.monotonic()
    draw(lines, TRIBUTARY)
    yield lambda: lines.query is None and not lines.waiting and lines.plot.view is not None and "Line 1" in lines.plot.view.heading and lines.plot.view.note
    waited = time.monotonic() - started
    view = lines.plot.view
    h.log(f"drawn line on the plot in {waited:.1f} s: {view.heading} {view.note}")
    h.log(f"limit: {view.limit[:400]}")
    record["drawn_line"] = {"heading": view.heading, "note": view.note, "limit": view.limit, "wait_s": waited, "peak_m3s": max(view.charts[0].curves[0].values)}
    h.check("the drawn line names its area, the two runs and their weights", "The line drains" in view.note and "km2, weight" in view.note, view.note)
    h.check("the drawn line's peak is read as the study reads a design point", "Peak " in view.note and "as the study reads a design point" in view.note, view.note)
    h.check("water on the drawn line", max(view.charts[0].curves[0].values) > 1.0, max(view.charts[0].curves[0].values))
    drawn = [[p.x(), p.y()] for p in list(lines._scratch().getFeatures())[-1].geometry().asPolyline()]
    record["drawn_line"]["coordinates"] = drawn
    h.check(
        f"the line went where it was clicked, within two pixels of {pixel:.1f} m",
        all(abs(a[0] - b[0]) <= 2 * pixel and abs(a[1] - b[1]) <= 2 * pixel for a, b in zip(drawn, TRIBUTARY, strict=False)), drawn,
    )  # fmt: skip
    h.widget_shot("study_line", lines)
    (h.P / "w53_dock.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
