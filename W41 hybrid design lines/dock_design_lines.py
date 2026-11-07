"""W41 through the real dock: a hybrid design line reads the lumped water that passes it.

Three cases, with the rules fixed before the runs (the constants below):
1. W39's hybrid on a basin generated from the DEM, Bidah 03 at 30 m, RP200 NetCDF. The design line's record is the grid
   plus the network junction's outflow, which a reach carries past the line. W39 read 0.69 m3/s on the line against
   410.2 in the network.
2. W39's PMP through the dock's HMS route, S13 lumped and the rest rain-on-grid. S13 now enters at the wadi outlet of
   its polygon, up the wadi from the dam line. The engine CLI with S13 moved by hand to W1's point gave 1,463.8 m3/s
   on the line, against 24.4 with the HMS icon.
3. The Block 2 hybrid at 80 m through the dock's HMS route, every subbasin lumped, the HMS 100-yr storm. Each of the
   five dam lines is compared with the same job on W1's validated outlets, run on the engine CLI.
"""

import csv
import json
import os
import subprocess
from pathlib import Path

import numpy as np

LINE = "Bidah 03"
DAMS = ("Bidah 03", "Faydh 01", "R5A", "R2A", "Z4C")
RP200 = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\Grid\netCDF\Precipitation_RP200_10min.nc")
W1_JOB = "arf_b20_n100.json"
RECORD_TOLERANCE = 5e-3
"""Case 1: the record's peak against the network junction's peak plus the grid line's at the same time."""
W39_NETWORK_PEAK = 410.16
"""Case 1: W39's network junction peak; the record must hold it within 1 %."""
S13_LINE_PEAK = 1463.8
S13_TOLERANCE = 0.02
"""Case 2: the dock's line against the CLI run with S13 at W1's point."""
DAM_TOLERANCE = 0.02
"""Case 3: each dam line against the same job on W1's outlets."""
RUN_LIMIT = 3000
HERE = Path(__file__).resolve().parent
VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")


def series(path, column):
    with Path(path).open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    t = np.array([float(r["t_s"]) for r in rows])
    return t, np.array([float(r[column]) for r in rows])


def peak(path, column):
    t, q = series(path, column)
    k = int(np.argmax(np.abs(q)))
    return float(abs(q[k])), float(t[k])


def settled(lines):
    return lambda: lines.query is None and not lines.waiting


def cli(h, job, out):
    """The engine CLI on this checkout, with the plugin's clean environment."""
    import sys

    if str(h.REPO / "plugin") not in sys.path:
        sys.path.insert(0, str(h.REPO / "plugin"))
    from wadi2d_qgis.protocol import clean_env

    env = clean_env(dict(os.environ))
    env["PYTHONPATH"] = str(h.REPO)
    exe = h.VENV.parent / "wadi2d.exe"
    args = [str(exe)] if exe.is_file() else [str(h.VENV), "-m", "wadi2d.engine.cli"]
    done = subprocess.run([*args, "run", str(job), "--out", str(out)], capture_output=True, text=True, env=env)
    return done.returncode, done.stderr[-2000:]


def scenario(h):
    h.TOTAL_LIMIT = 14400.0
    h.STEP_LIMIT = 3600.0
    if not h.VENV.is_file():
        h.VENV = VENV
    ground = h.Bidah()
    summary = {}
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    coordinates = next(k["coordinates"] for k in jobs["outputs"]["lines"] if k["name"] == LINE)
    line = h.add_vector(h.geojson("bidah_line", [h.line(coordinates, name=LINE)]), "Bidah 03 line", ground.crs)
    cn = h.add_raster(h.BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn")
    dock = yield from h.open_dock()
    hy, storm, box = dock.hydrology, dock.storm, dock.hydrology.basin

    def finished(folder, label):
        done = h.events(folder, "done")
        ok = bool(done) and done[-1].get("code") == 0
        h.check(f"{label}: the run finished", ok, dock.panel.message.text()[:300])
        return ok

    h.log("=== 1 a generated basin: the design line's record holds the network's water")
    h.set_rain_job(dock, ground, h.RUNS / "generated", dx=30.0, rain=10.0, hours=1.0, sim_hours=30.0, pixels=False)
    dock.points.layer.setLayer(line)
    dock.points.name.setField("name")
    hy.cn.raster.setLayer(cn)
    storm.kind.setCurrentIndex(storm.kind.findData("gridded"))
    storm.is_folder.setCurrentIndex(0)
    storm.rain_file.setFilePath(str(RP200))
    yield lambda: storm.rain_label.text() and "Reading" not in storm.rain_label.text()
    folder = h.RUNS / "generated"
    dock.panel.folder.setFilePath(str(folder))
    box.setChecked(True)
    box.threshold.setValue(2.0)
    box.generate_button.click()
    yield lambda: box.generate_button.isEnabled()
    h.check("a basin was generated with the design line as a junction", box.model is not None and any(e["name"] == LINE for e in box.model["elements"]), box.summary.text())
    yield from h.run(dock, RUN_LIMIT)
    if finished(folder, "generated"):
        record = folder / "series" / "design_Bidah_03.csv"
        h.check("the run wrote the design line's record", record.is_file(), sorted(p.name for p in (folder / "series").glob("*")))
        if record.is_file():
            t, total = series(record, "total_m3s")
            _, grid = series(record, "grid_m3s")
            tn, net = series(folder / "series" / "network_Bidah_03.csv", "outflow_m3s")
            expect = np.abs(np.interp(t, tn, net) - grid)
            got = float(np.abs(total).max())
            h.log(f"record peak {got:.1f} m3/s; grid alone {np.abs(grid).max():.2f}; network {np.abs(net).max():.1f}")
            h.check("the record is the grid plus the network, within 0.5 %", abs(got / expect.max() - 1.0) < RECORD_TOLERANCE, (got, float(expect.max())))
            h.check("the record holds W39's network peak within 1 %", abs(got / W39_NETWORK_PEAK - 1.0) < 0.01, got)
            design = h.events(folder, "design")
            h.check("the run names the record and its junction", bool(design) and design[-1]["elements"] == [LINE], design)
            summary["generated"] = {"record_peak": got, "grid_peak": float(np.abs(grid).max()), "network_peak": float(np.abs(net).max())}
        dock.panel.lines_button.click()
        lines = dock.line_panel
        yield settled(lines)
        labels = [lines.choice.itemText(i) for i in range(lines.choice.count())]
        pick = next((i for i, text in enumerate(labels) if LINE in text and "Lumped" not in text), None)
        h.check("the panel offers the design line", pick is not None, labels[:6])
        if pick is not None:
            lines.choice.setCurrentIndex(pick)
            yield settled(lines)
            view = lines.plot.view
            curves = view.charts[0].curves if view is not None else []
            h.check("the panel draws the record and the grid alone", len(curves) >= 2 and "lumped water" in curves[0].label, [c.label for c in curves])
            if curves:
                h.check("its peak is the record's", abs(max(curves[0].values) - summary["generated"]["record_peak"]) <= 0.01 * summary["generated"]["record_peak"] + 0.1, max(curves[0].values))
            h.check("its words say why", "inside a reach" in view.limit, view.limit[:200])
            h.widget_shot("record_Bidah_03", lines.plot)
        lines.close()
    box.setChecked(False)

    h.log("=== 2 the HMS route: S13 enters up the wadi from the dam line")
    hy.folder.setFilePath(str(h.BLOCK / "HEC_HMS_Block_02"))
    yield lambda: hy.files["basin"].count() > 0
    hy.files["met"].setCurrentText("FM_PMP.met")
    storm.kind.setCurrentIndex(storm.kind.findData("hms"))
    for r in range(hy.table.rowCount()):
        hy.table.cellWidget(r, 1).setCurrentText("lumped" if hy.table.item(r, 0).text() == "S13" else "2d")
    folder = h.RUNS / "pmp_hybrid"
    dock.panel.folder.setFilePath(str(folder))
    yield from h.run(dock, RUN_LIMIT)
    if finished(folder, "pmp_hybrid"):
        imported = json.loads((folder / "hms_import.json").read_text(encoding="utf-8"))
        h.check("the HMS import asks for wadi entries", {s.get("entry") for s in imported["hydrology"]["subbasins"]} == {"wadi"}, imported["hydrology"]["subbasins"][:2])
        placed = json.loads((folder / "entries.json").read_text(encoding="utf-8"))
        s13 = next(p for p in placed if p["name"] == "S13")
        h.log(f"S13: {s13}")
        h.check("S13 moved off the HMS icon, clear of the lines", s13["clear"] and s13["moved_m"] > 50.0, s13)
        got, at = peak(folder / "series" / "line_Bidah_03.csv", "discharge_m3s")
        h.log(f"Bidah 03 line peak {got:.1f} m3/s at {at / 3600:.2f} h")
        h.check(f"the Bidah 03 line within {S13_TOLERANCE:.0%} of {S13_LINE_PEAK}", abs(got / S13_LINE_PEAK - 1.0) < S13_TOLERANCE, got)
        summary["pmp_hybrid"] = {"line_peak": got, "s13": s13}

    h.log("=== 3 the Block 2 hybrid at 80 m: the five dam lines against W1's outlets")
    domain = h.add_vector(h.VALIDATION / "domain.geojson", "domain block 2", ground.crs)
    outlets = h.add_vector(h.geojson("outs", [h.line(k["coordinates"], kind="normal", value=0.008) for k in jobs["boundaries"]]), "block outlets", ground.crs)
    rings = h.add_vector(h.geojson("dams", [h.line(k["coordinates"], name=k["name"]) for k in jobs["outputs"]["lines"]]), "block dams", ground.crs)
    t = dock.terrain
    t.domain.setLayer(domain)
    t.dx.setValue(80.0)
    hy.files["met"].setCurrentText("FM_100yr.met")
    storm.kind.setCurrentIndex(storm.kind.findData("hms"))
    for r in range(hy.table.rowCount()):
        hy.table.cellWidget(r, 1).setCurrentText("lumped")
    dock.boundaries.layer.setLayer(outlets)
    dock.points.layer.setLayer(rings)
    dock.points.name.setField("name")
    dock.panel.duration.setValue(30.0)
    folder = h.RUNS / "block2"
    dock.panel.folder.setFilePath(str(folder))
    yield from h.run(dock, RUN_LIMIT)
    if finished(folder, "block2"):
        warned = [e["message"] for e in h.events(folder, "warn") if "pond's surge" in e.get("message", "")]
        on_dams = [m for m in warned if any(m.startswith(f"line {d} crosses") for d in DAMS)]
        h.check("no dam line crosses a lumped inflow's cells any more", not on_dams, on_dams)
        job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        w1 = json.loads((h.VALIDATION / "jobs" / W1_JOB).read_text(encoding="utf-8"))
        outlets_w1 = {s["name"]: s["outlet"] for s in w1["hydrology"]["subbasins"]}
        for sub in job["hydrology"]["subbasins"]:
            sub["outlet"], sub["entry"] = outlets_w1[sub["name"]], "point"
        reference = h.P / "block2_w1.json"
        reference.write_text(json.dumps(job, indent=2), encoding="utf-8")
        code, err = cli(h, reference, h.RUNS / "block2_w1")
        h.check("the reference on W1's outlets ran", code == 0, err)
        rows = {}
        for dam in DAMS:
            name = dam.replace(" ", "_")
            got, _ = peak(folder / "series" / f"line_{name}.csv", "discharge_m3s")
            ref, _ = peak(h.RUNS / "block2_w1" / "series" / f"line_{name}.csv", "discharge_m3s") if code == 0 else (float("nan"), 0)
            path = folder / "series" / f"network_{name}.csv"  # gone since the HMS route writes only what entered
            net = peak(path, "outflow_m3s")[0] if path.is_file() else float("nan")
            rows[dam] = {"dock": got, "w1": ref, "network": net, "ratio": got / ref if ref else float("nan")}
            h.log(f"{dam}: dock {got:.1f}, W1's outlets {ref:.1f}, ratio {got / ref:.4f}; lumped network {net:.1f}")
            h.check(f"{dam} within {DAM_TOLERANCE:.0%} of W1's outlets", abs(got / ref - 1.0) < DAM_TOLERANCE, rows[dam])
        summary["block2"] = rows
    (h.P / "w41_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
