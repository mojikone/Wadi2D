"""Face frames through the real dock: a line drawn after the run reads the upfront line's number at the frames.

Extends W21's check. Four upfront lines, across, oblique, along the axis and bent, each read back from the saved faces
against its own series; a drawn line and a line from a layer that say they are of record; the same job rerun without the
faces for the disk cost and for the fallback through the dock; a mesh.
"""

import csv
import json
import os
import subprocess

import numpy as np
from qgis.core import QgsProject
from qgis.gui import QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QPoint, Qt
from qgis.utils import iface

ACROSS = [[438431.5, 2727194.4], [438720.5, 2726786.4]]
OBLIQUE = [[438329.6, 2727032.5], [438822.4, 2726948.3]]
AXIS = [[438259.32, 2727264.77], [438807.68, 2726752.81]]
BENT = [[438100.0, 2727420.0], [438259.32, 2727264.77], [438807.68, 2726752.81], [438870.0, 2726640.0]]
"""The Bidah 03 dam line of the validation jobs: four vertices, two bends."""
UPFRONT = (("Across", ACROSS), ("Oblique", OBLIQUE), ("Axis", AXIS), ("Bent", BENT))
DRAWN = [[437371.8, 2726700.4], [437376.0, 2726450.0], [437380.2, 2726200.4]]
FROM_LAYER = [[434738.3, 2726827.9], [435213.7, 2726672.9]]
RUNNING = 0.25
"""Frames where the record stands above this share of its peak are compared one by one."""
WITHIN = 0.01
OF_RECORD = "number of record at the frame interval"
"""In the footer."""
LABEL = "from the faces, of record"
"""In the legend, short enough for its box."""


def engine_is_this_worktree(h):
    from wadi2d_qgis.protocol import clean_env

    code = f"import sys; sys.path.insert(0, r'{h.REPO}'); import wadi2d; print(wadi2d.__file__)"
    done = subprocess.run([str(h.VENV), "-c", code], capture_output=True, text=True, check=True, env=clean_env(dict(os.environ)))
    return done.stdout.strip()


def engine_run(h, job, out):
    """The same engine the dock uses, on a job file, to the end."""
    from wadi2d_qgis.protocol import clean_env

    args = [str(h.VENV), str(h.P / "engine.py"), "run", str(job), "--out", str(out)]
    done = subprocess.run(args, capture_output=True, text=True, env=clean_env(dict(os.environ)))
    return done.returncode, done.stdout[-400:], done.stderr[-400:]


def click(canvas, tool, x, y, button):
    pixel = canvas.getCoordinateTransform().transform(x, y)
    point = QPoint(round(pixel.x()), round(pixel.y()))
    tool.canvasReleaseEvent(QgsMapMouseEvent(canvas, QEvent.MouseButtonRelease, point, button))


def draw(lines, coordinates):
    lines.draw_button.click()
    canvas = lines.canvas
    tool = canvas.mapTool()
    assert tool is lines.tool
    for x, y in coordinates:
        click(canvas, tool, x, y, Qt.LeftButton)
    click(canvas, tool, *coordinates[-1], Qt.RightButton)


def settled(lines):
    return lambda: lines.query is None and not lines.waiting


def series(folder, name):
    with (folder / "series" / f"{name}.csv").open() as f:
        return list(csv.DictReader(f))


def flow_of(view, source):
    return next(c for c in view.charts[0].curves if c.source == source)


def against_record(view, rows):
    """Peak ratio and the worst ratio over the running frames, frames against the series at the frame times."""
    t_record = np.array([float(r["t_s"]) for r in rows])
    q_record = np.abs(np.array([float(r["discharge_m3s"]) for r in rows]))
    frames = flow_of(view, "frames")
    at_frames = np.interp(np.array(frames.times_h) * 3600.0, t_record, q_record)
    read = np.array(frames.values)
    running = at_frames > RUNNING * at_frames.max()
    ratios = read[running] / at_frames[running]
    return read.max() / at_frames.max(), float(np.abs(ratios - 1.0).max()), int(running.sum())


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()
    panel = dock.panel
    project = QgsProject.instance()
    h.check("engine from this worktree", str(h.REPO) in engine_is_this_worktree(h), engine_is_this_worktree(h))
    design = h.add_vector(h.geojson("design", [h.line(c, name=n) for n, c in UPFRONT]), "upfront lines", ground.crs)
    other = h.add_vector(h.geojson("other", [h.line(FROM_LAYER, name="Upstream")]), "other lines", ground.crs)
    extent = ground.domain.extent()
    iface.mapCanvas().setExtent(extent)

    h.log("=== 1 a run with four upfront lines; the faces are in the run")
    h.set_rain_job(dock, ground, "uniform", rain=60.0, hours=1.0, sim_hours=2.0, pixels=False)
    dock.points.layer.setLayer(design)
    dock.points.name.setField("name")
    panel.maps.setCurrentIndex(1)  # every five minutes
    yield from h.run(dock)
    folder = h.RUNS / "uniform"
    h.check("finished", h.events(folder, "done")[-1]["code"] == 0, panel.message.text())
    resolved = json.loads((folder / "config.resolved.json").read_text(encoding="utf-8"))
    h.check("the job kept the faces by default", resolved["outputs"]["face_discharge"] is True)
    cells = h.events(folder, "start")[-1]["cells"]
    panel.lines_button.click()
    lines = dock.line_panel
    h.check("the panel opened", lines is not None and lines.isVisible())
    yield settled(lines)
    names = [lines.choice.itemText(i) for i in range(lines.choice.count())]
    h.check("the four upfront lines are listed", names[:4] == [f"Upfront line: {n}" for n, _ in UPFRONT], names)
    maps = len(lines.plot.view.frames_s)

    h.log("=== 2 each upfront line read back from the faces against its own series")
    table = {}
    for index, (name, _) in enumerate(UPFRONT):
        lines.choice.setCurrentIndex(index)
        yield settled(lines)
        view = lines.plot.view
        frames = flow_of(view, "frames")
        h.check(f"{name}: labelled of record", LABEL in frames.label, frames.label)
        h.check(f"{name}: the footer says so", OF_RECORD in view.limit and "estimated" not in view.limit, view.limit)
        rows = series(folder, f"line_{name}")
        peak, worst, count = against_record(view, rows)
        table[name] = {"record_peak": max(abs(float(r["discharge_m3s"])) for r in rows), "frames_peak": max(frames.values), "peak_ratio": peak, "worst_off_record": worst, "running_frames": count}
        h.log(f"{name}: record peak {table[name]['record_peak']:.1f}, frames {table[name]['frames_peak']:.1f}, peak ratio {peak:.4f}, worst over {count} running frames {worst:.4f}")
        h.check(f"{name}: peak within 1 %", abs(peak - 1.0) < WITHIN, peak)
        h.check(f"{name}: every running frame within 1 %", worst < WITHIN, worst)
    lines.choice.setCurrentIndex(0)
    yield settled(lines)
    lines.slider.setValue(lines.slider.maximum() * 7 // 12)
    h.widget_shot("upfront_line_of_record", lines.plot)

    h.log("=== 3 a line drawn after the run, and one from a layer")
    draw(lines, DRAWN)
    yield settled(lines)
    view = lines.plot.view
    h.check("drawn line chosen", lines.choice.currentText() == "Temporary line: Line 1", lines.choice.currentText())
    h.check("drawn line is of record", LABEL in flow_of(view, "frames").label and OF_RECORD in view.limit, view.limit)
    h.check("no record curve on it", {c.source for c in view.charts[0].curves} == {"frames"})
    h.check("water on it", max(view.charts[0].curves[0].values) > 1.0, max(view.charts[0].curves[0].values))
    lines.slider.setValue(14)
    h.widget_shot("temporary_line_of_record", lines.plot)
    lines.layer.setLayer(other)
    lines.use_button.click()
    yield settled(lines)
    view = lines.plot.view
    h.check("a line from a layer is of record too", LABEL in flow_of(view, "frames").label, flow_of(view, "frames").label)
    h.check("flow on it", max(view.charts[0].curves[0].values) > 1.0, max(view.charts[0].curves[0].values))

    h.log("=== 4 the same job without the faces: the disk cost, and the fallback through the dock")
    resolved["outputs"]["face_discharge"] = False
    job = h.P / "nofaces.json"
    job.write_text(json.dumps(resolved), encoding="utf-8")
    code, out, err = engine_run(h, job, h.RUNS / "nofaces")
    h.check("the run without faces finished", code == 0, (code, out, err))
    with_faces = (folder / "results.h5").stat().st_size
    without = (h.RUNS / "nofaces" / "results.h5").stat().st_size
    disk = {
        "cells": cells, "maps": maps, "results_h5_with_faces_bytes": with_faces, "results_h5_without_bytes": without,
        "bytes_per_cell_per_map_with": with_faces / cells / maps, "bytes_per_cell_per_map_without": without / cells / maps,
        "faces_share_of_file": (with_faces - without) / with_faces, "faces_bytes_per_cell_per_map": (with_faces - without) / cells / maps,
    }  # fmt: skip
    h.log(f"disk: {json.dumps(disk)}")
    h.check("the faces cost disk", with_faces > without, (with_faces, without))
    panel.folder.setFilePath(str(h.RUNS / "nofaces"))
    panel.lines_button.click()
    yield settled(lines)
    h.check("the run without faces is read", lines.run == h.RUNS / "nofaces", lines.run)
    lines.choice.setCurrentIndex(0)
    yield settled(lines)
    view = lines.plot.view
    frames = flow_of(view, "frames")
    h.check("on it the frames curve says estimated", frames.label == "Saved frames, every 5 min: estimated", frames.label)
    h.check("and the footer keeps the old limit", "not a number of record" in view.limit and OF_RECORD not in view.limit, view.limit)
    rows = series(h.RUNS / "nofaces", "line_Across")
    peak, worst, count = against_record(view, rows)
    table["Across, estimate"] = {"record_peak": max(abs(float(r["discharge_m3s"])) for r in rows), "frames_peak": max(frames.values), "peak_ratio": peak, "worst_off_record": worst, "running_frames": count}
    h.log(f"Across without faces: estimate peak ratio {peak:.4f}, worst {worst:.4f}")
    h.widget_shot("estimate_fallback", lines.plot)

    h.log("=== 5 a mesh")
    m = dock.mesh
    m.setCollapsed(False)
    h.set_rain_job(dock, ground, "mesh", dx=10.0, rain=60.0, hours=1.0, sim_hours=1.5, pixels=False)
    dock.points.layer.setLayer(design)
    dock.points.name.setField("name")
    m.enabled.setChecked(True)
    m.coarse.setValue(40.0)
    panel.maps.setCurrentIndex(1)
    yield from h.run(dock)
    yield settled(lines)
    h.check("the mesh run is read", lines.run == h.RUNS / "mesh", lines.run)
    for index, (name, _) in enumerate(UPFRONT):
        lines.choice.setCurrentIndex(index)
        yield settled(lines)
        view = lines.plot.view
        rows = series(h.RUNS / "mesh", f"line_{name}")
        peak, worst, count = against_record(view, rows)
        table[f"{name}, mesh"] = {"record_peak": max(abs(float(r["discharge_m3s"])) for r in rows), "frames_peak": max(flow_of(view, "frames").values), "peak_ratio": peak, "worst_off_record": worst, "running_frames": count}
        h.log(f"mesh {name}: peak ratio {peak:.4f}, worst over {count} running frames {worst:.4f}")
        h.check(f"mesh {name}: of record, within 1 %", LABEL in flow_of(view, "frames").label and abs(peak - 1.0) < WITHIN and worst < WITHIN, (peak, worst))
    draw(lines, DRAWN)
    yield settled(lines)
    view = lines.plot.view
    h.check("a drawn line on the mesh reads the faces", LABEL in flow_of(view, "frames").label and max(view.charts[0].curves[0].values) > 1.0, max(view.charts[0].curves[0].values))
    h.widget_shot("mesh_line", lines.plot)
    (h.P / "table.json").write_text(json.dumps({"lines": table, "disk": disk}, indent=2), encoding="utf-8")

    h.log("=== 6 the panel goes with the plugin")
    folder = lines.folder
    dock.release()
    h.check("released", dock.line_panel is None)
    h.check("its files are gone", not os.path.exists(folder), folder)
    m.enabled.setChecked(False)
    project.setDirty(False)
