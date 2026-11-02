"""D9 through the real dock: upfront lines and points, a drawn line, a line from a layer, all following the time slider."""

import csv
import json
import os
import subprocess
import time

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsMeshDatasetIndex,
    QgsPointXY,
    QgsProject,
    QgsTemporalNavigationObject,
)
from qgis.gui import QgsMapMouseEvent
from qgis.PyQt.QtCore import QEvent, QPoint, Qt
from qgis.utils import iface

ACROSS = [[438431.5, 2727194.4], [438720.5, 2726786.4]]
OBLIQUE = [[438329.6, 2727032.5], [438822.4, 2726948.3]]
AXIS = [[438259.32, 2727264.77], [438807.68, 2726752.81]]
DRAWN = [[437371.8, 2726700.4], [437376.0, 2726450.0], [437380.2, 2726200.4]]
POOL = [438700.0, 2727060.0]
FROM_LAYER = [[434738.3, 2726827.9], [435213.7, 2726672.9]]


def engine_is_this_worktree(h):
    from wadi2d_qgis.protocol import clean_env

    code = f"import sys; sys.path.insert(0, r'{h.REPO}'); import wadi2d; print(wadi2d.__file__)"
    done = subprocess.run([str(h.VENV), "-c", code], capture_output=True, text=True, check=True, env=clean_env(dict(os.environ)))
    return done.stdout.strip()


def click(canvas, tool, x, y, button):
    pixel = canvas.getCoordinateTransform().transform(x, y)
    point = QPoint(round(pixel.x()), round(pixel.y()))
    tool.canvasReleaseEvent(QgsMapMouseEvent(canvas, QEvent.MouseButtonRelease, point, button))


def draw(lines, coordinates):
    """Through the real map tool, as clicks on the canvas."""
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
        rows = list(csv.DictReader(f))
    return rows


def flow_of(view, source):
    return next(c for c in view.charts[0].curves if c.source == source)


def peak_ratio(view):
    return max(flow_of(view, "frames").values) / max(flow_of(view, "upfront").values)


def frames_layer(h, run):
    return next(n.layer() for n in h.group_of(run).findLayers() if n.layer().name() == "Flood over time, cells")


def depth_group(layer):
    provider = layer.dataProvider()
    for g in range(provider.datasetGroupCount()):
        if provider.datasetGroupMetadata(QgsMeshDatasetIndex(g, 0)).name().lower().startswith("depth"):
            return g
    return -1


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()
    panel = dock.panel
    project = QgsProject.instance()
    h.check("engine from this worktree", str(h.REPO) in engine_is_this_worktree(h), engine_is_this_worktree(h))
    h.check("engine.py names this worktree", str(h.REPO) in (h.P / "engine.py").read_text(), (h.P / "engine.py").read_text()[:90])
    design = h.add_vector(
        h.geojson("design", [h.line(ACROSS, name="Across"), h.line(OBLIQUE, name="Oblique"), h.line(AXIS, name="Axis")]),
        "upfront lines", ground.crs,
    )  # fmt: skip
    other = h.add_vector(h.geojson("other", [h.line(FROM_LAYER, name="Upstream")]), "other lines", ground.crs)
    points = h.add_vector(
        h.geojson("points", [{"type": "Feature", "properties": {"name": "Pool"}, "geometry": {"type": "Point", "coordinates": POOL}}]),
        "upfront points", ground.crs,
    )  # fmt: skip
    extent = ground.domain.extent()
    iface.mapCanvas().setExtent(extent)

    h.log("=== 1 a run with upfront lines; the button and the panel")
    h.check("no button before a run", not panel.lines_button.isEnabled())
    h.set_rain_job(dock, ground, "uniform", rain=60.0, hours=1.0, sim_hours=2.0, pixels=False)
    dock.points.layer.setLayer(design)
    dock.points.name.setField("name")
    panel.maps.setCurrentIndex(1)  # every five minutes
    yield from h.run(dock)
    folder = h.RUNS / "uniform"
    h.check("finished", h.events(folder, "done")[-1]["code"] == 0, panel.message.text())
    h.check("button after a run", panel.lines_button.isEnabled())
    h.check("nothing new in the run folder", not (folder / "frames.nc").exists())
    before = sorted(p.name for p in folder.iterdir())
    panel.lines_button.click()
    lines = dock.line_panel
    h.check("the panel opened", lines is not None and lines.isVisible())
    yield settled(lines)
    h.check("a run's upfront lines are listed", [lines.choice.itemText(i) for i in range(lines.choice.count())][:3] == ["Upfront line: Across", "Upfront line: Oblique", "Upfront line: Axis"], lines.choice.count())
    yield settled(lines)
    view = lines.plot.view
    h.check("the first line shows", view is not None and view.heading.startswith("Upfront line: Across"), view.heading)
    h.check("both kinds in the flow chart", {c.source for c in view.charts[0].curves} == {"upfront", "frames"})
    h.check("each labelled in the plot", any("number of record" in c.label for c in view.charts[0].curves) and any("Saved frames, every 5 min: estimated" in c.label for c in view.charts[0].curves), [c.label for c in view.charts[0].curves])
    h.check("the limit is stated", "every 5 min" in view.limit and "estimated from depth and speed" in view.limit, view.limit)
    h.check("depth and a section", len(view.charts) == 2 and view.section is not None)
    h.check("nothing added to the run folder", sorted(p.name for p in folder.iterdir()) == before)
    h.check("a frame per saved map", len(view.frames_s) == lines.slider.maximum() + 1, (len(view.frames_s), lines.slider.maximum()))

    h.log("=== 2 flow from frames against the record, the limit that is stated")
    ratios = {}
    for index, name in enumerate(("Across", "Oblique", "Axis")):
        lines.choice.setCurrentIndex(index)
        yield settled(lines)
        view = lines.plot.view
        rows = series(folder, f"line_{name}")
        record = max(abs(float(r["discharge_m3s"])) for r in rows)
        h.check(f"{name}: the plot holds the record of the run", abs(max(flow_of(view, "upfront").values) - record) < 0.01 * record + 0.01, record)
        ratios[name] = peak_ratio(view)
        h.log(f"{name}: record peak {record:.1f}, frames {max(flow_of(view, 'frames').values):.1f}, ratio {ratios[name]:.3f}")
    (h.P / "ratios.json").write_text(json.dumps(ratios), encoding="utf-8")
    h.check("a line square to the flow stands within 10 %", abs(ratios["Across"] - 1.0) < 0.10, ratios["Across"])
    h.check("the long axis stands within 10 %", abs(ratios["Axis"] - 1.0) < 0.10, ratios["Axis"])
    h.check("an oblique line stands within 30 %", abs(ratios["Oblique"] - 1.0) < 0.30, ratios["Oblique"])
    lines.choice.setCurrentIndex(0)
    yield settled(lines)
    lines.slider.setValue(lines.slider.maximum() * 7 // 12)
    h.widget_shot("upfront_line", lines.plot)
    h.widget_shot("panel_upfront", lines)

    h.log("=== 3 a temporary line, drawn through the real map tool")
    h.check("no temporary layer yet", not [n for n in project.mapLayers().values() if n.name() == "Temporary result lines"])
    started = time.monotonic()
    draw(lines, DRAWN)
    h.check("the map tool let go", iface.mapCanvas().mapTool() is not lines.tool)
    yield settled(lines)
    h.log(f"drawn line on the plot in {time.monotonic() - started:.1f} s, a quarter second of it this check's own wait")
    h.check("the drawn line is chosen", lines.choice.currentText() == "Temporary line: Line 1", lines.choice.currentText())
    view = lines.plot.view
    h.check("labelled temporary", view.heading.startswith("Temporary line: Line 1. Read from saved frames"), view.heading)
    h.check("no record on a temporary line", {c.source for c in view.charts[0].curves} == {"frames"})
    h.check("the limit is on it too", "every 5 min" in view.limit and "not a number of record" in view.limit)
    h.check("water on it", max(view.charts[0].curves[0].values) > 1.0 and max(view.charts[1].curves[0].values) > 0.1, max(view.charts[0].curves[0].values))
    scratch = next(n for n in project.mapLayers().values() if n.name() == "Temporary result lines")
    drawn = [list(p) for p in next(scratch.getFeatures()).geometry().asPolyline()]
    tolerance = iface.mapCanvas().mapUnitsPerPixel() + 1.0
    h.check("the line went where it was clicked", all(abs(a[0] - b[0]) < tolerance and abs(a[1] - b[1]) < tolerance for a, b in zip(drawn, DRAWN, strict=True)), drawn)
    node = project.layerTreeRoot().findLayer(scratch)
    h.check("the layer sits on top of the run's group", node.parent().name() == "uniform" and node.parent().children()[0] == node)
    h.check("it is a scratch layer", scratch.isTemporary())
    lines.slider.setValue(14)
    h.widget_shot("temporary_line", lines.plot)
    h.check("in the run's CRS", scratch.crs() == ground.crs, scratch.crs().authid())
    h.check("the panel does not offer it as a layer", scratch not in [lines.layer.layer(i) for i in range(lines.layer.count())])

    h.log("=== 4 a line picked from a layer")
    lines.layer.setLayer(other)
    h.check("its lines are listed", lines.feature.count() == 1 and lines.feature.currentText() == "Upstream", lines.feature.currentText())
    lines.use_button.click()
    yield settled(lines)
    h.check("it is a temporary line", lines.choice.currentText() == "Temporary line: Upstream, from other lines", lines.choice.currentText())
    view = lines.plot.view
    h.check("read from frames", view.section is not None and {c.source for c in view.charts[0].curves} == {"frames"})
    h.check("flow on it", max(view.charts[0].curves[0].values) > 1.0, max(view.charts[0].curves[0].values))
    h.check("not added to the scratch layer", scratch.featureCount() == 1, scratch.featureCount())

    h.log("=== 4b another CRS, on a layer and on the map")
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    to_wgs84 = QgsCoordinateTransform(ground.crs, wgs84, project)
    degrees = [[(p := to_wgs84.transform(QgsPointXY(x, y))).x(), p.y()] for x, y in FROM_LAYER]
    foreign = h.add_vector(h.geojson("foreign", [h.line(degrees, name="Degrees")], epsg=4326), "degrees", wgs84)
    lines.layer.setLayer(foreign)
    lines.use_button.click()
    yield settled(lines)
    h.check("a layer in another CRS reads the same line", abs(max(lines.plot.view.charts[0].curves[0].values) - max(view.charts[0].curves[0].values)) < 0.02 * max(view.charts[0].curves[0].values), max(lines.plot.view.charts[0].curves[0].values))
    canvas = iface.mapCanvas()
    canvas.setDestinationCrs(wgs84)
    canvas.setExtent(to_wgs84.transformBoundingBox(extent))
    draw(lines, [[(p := to_wgs84.transform(QgsPointXY(x, y))).x(), p.y()] for x, y in DRAWN])
    yield settled(lines)
    h.check("a map in another CRS draws in the run's", lines.choice.currentText() == "Temporary line: Line 2", lines.choice.currentText())
    latest = [f for f in scratch.getFeatures() if f["name"] == "Line 2"][0].geometry().asPolyline()
    slack = 2.0 * canvas.mapUnitsPerPixel() * 111000.0
    h.check("in metres, where it was clicked", abs(latest[0].x() - DRAWN[0][0]) < slack and abs(latest[0].y() - DRAWN[0][1]) < slack, (latest[0].x(), latest[0].y(), slack))
    lines.remove_button.click()
    yield settled(lines)
    canvas.setDestinationCrs(ground.crs)
    canvas.setExtent(extent)

    h.log("=== 5 it moves with the time slider")
    h.check("the panel works before the Time slider button", lines.slider.isEnabled())
    lines.choice.setCurrentIndex(0)
    yield settled(lines)
    panel.message.clear()
    panel.frames_button.click()
    yield lambda: panel.frames_button.isEnabled() and "Temporal Controller" in panel.message.text()
    layer = frames_layer(h, "uniform")
    controller = iface.mapCanvas().temporalController()
    h.check("the controller is set", controller.navigationMode() == QgsTemporalNavigationObject.Animated)
    group = depth_group(layer)
    mismatches = 0
    sections = set()
    for number in range(controller.totalFrameCount()):
        controller.setCurrentFrameNumber(number)
        picked = layer.datasetIndexAtTime(controller.dateTimeRangeForFrameNumber(number), group).dataset()
        if picked != lines.frame:
            mismatches += 1
            h.log(f"step {number}: map shows {picked}, plot {lines.frame}")
        sections.add(json.dumps(lines.plot.view.section.level_m[lines.plot.frame]))
    h.check("at every step the plot shows the frame the map shows", mismatches == 0, mismatches)
    h.check("the water surface changes as it moves", len(sections) > 10, len(sections))
    controller.setCurrentFrameNumber(3)
    early = (lines.frame, lines.plot.frame, lines.time_label.text())
    controller.setCurrentFrameNumber(14)
    late = (lines.frame, lines.plot.frame, lines.time_label.text())
    h.check("the cursor and the clock move", early[0] != late[0] and early[1] != late[1] and early[2] != late[2], (early, late))
    h.widget_shot("frame_14", lines.plot)
    controller.setCurrentFrameNumber(3)
    h.widget_shot("frame_03", lines.plot)
    lines.slider.setValue(14)
    h.check("the panel's own slider moves the map", controller.currentFrameNumber() in (13, 14, 15), controller.currentFrameNumber())
    wrong = 0
    for frame in range(lines.slider.maximum()):  # the controller's last step starts before the last frame: see the README
        lines.slider.setValue(frame)
        number = controller.currentFrameNumber()
        if layer.datasetIndexAtTime(controller.dateTimeRangeForFrameNumber(number), group).dataset() != frame:
            wrong += 1
    h.check("each frame of the panel's slider shows on the map", wrong == 0, wrong)
    lines.slider.setValue(14)
    moved = iface.mapCanvas().temporalRange().begin()
    h.check("and the canvas with it", moved == controller.dateTimeRangeForFrameNumber(controller.currentFrameNumber()).begin())
    begin = layer.temporalProperties().timeExtent().begin()
    h.render("map_with_lines", [scratch, design, layer, ground.dem], extent.center(), 40000, temporal=begin.addSecs(14 * 300))
    h.render("map_near_drawn", [scratch, layer, ground.dem], QgsPointXY(*DRAWN[1]), 8000, temporal=begin.addSecs(14 * 300))
    h.widget_shot("panel_temporary", lines)
    h.shot("window")

    h.log("=== 6 a line that misses the model, and removing a line")
    draw(lines, [[extent.xMinimum() - 3000.0, extent.yMinimum()], [extent.xMinimum() - 500.0, extent.yMinimum()]])
    yield settled(lines)
    h.check("off the model says so", "does not cross the model" in lines.message.text(), lines.message.text())
    h.check("two lines on the scratch layer", scratch.featureCount() == 2, scratch.featureCount())
    h.check("named on", lines.choice.currentText() == "Temporary line: Line 3", lines.choice.currentText())
    lines.remove_button.click()
    yield settled(lines)
    h.check("removed from the list and the layer", scratch.featureCount() == 1 and "Temporary line: Line 3" not in [lines.choice.itemText(i) for i in range(lines.choice.count())], scratch.featureCount())
    lines.choice.setCurrentIndex(0)
    h.check("an upfront line has no remove", not lines.remove_button.isEnabled())

    h.log("=== 7 upfront points")
    h.set_rain_job(dock, ground, "points", rain=60.0, hours=0.5, sim_hours=1.0, pixels=False)
    dock.points.layer.setLayer(points)
    dock.points.name.setField("name")
    panel.maps.setCurrentIndex(1)
    yield from h.run(dock)
    yield settled(lines)
    folder = h.RUNS / "points"
    h.check("the panel follows the new run", lines.run == folder, lines.run)
    names = [lines.choice.itemText(i) for i in range(lines.choice.count())]
    h.check("the point is listed, and the temporary lines stay", names[0] == "Upfront point: Pool" and "Temporary line: Line 1" in names, names)
    lines.choice.setCurrentIndex(0)
    yield settled(lines)
    view = lines.plot.view
    h.check("labelled upfront", view.heading.startswith("Upfront point: Pool") and "number of record" in view.limit, view.heading)
    h.check("depth and level, no section", len(view.charts) == 2 and view.section is None)
    rows = series(folder, "point_Pool")
    h.check("the record of the run", abs(max(view.charts[0].curves[0].values) - max(float(r["depth_m"]) for r in rows)) < 0.01)
    h.widget_shot("upfront_point", lines.plot)
    temporary = names.index("Temporary line: Line 1")
    lines.choice.setCurrentIndex(temporary)
    yield settled(lines)
    h.check("a temporary line reads the new run", lines.plot.view.heading.startswith("Temporary line: Line 1"), lines.plot.view.heading)

    h.log("=== 8 too few frames")
    h.set_rain_job(dock, ground, "few", rain=60.0, hours=0.2, sim_hours=0.05, pixels=False)
    dock.points.layer.setLayer(design)
    dock.points.name.setField("name")
    panel.maps.setCurrentIndex(0)
    yield from h.run(dock)
    yield settled(lines)
    h.check("the upfront line still shows its record", lines.plot.view is not None and lines.plot.view.section is None, lines.message.text())
    h.check("and says why there is no reading from frames", "a line needs two" in lines.message.text(), lines.message.text())

    h.log("=== 9 a finished run chosen by its folder")
    panel.folder.setFilePath(str(h.RUNS / "uniform"))
    panel.lines_button.click()
    yield settled(lines)
    h.check("back on the first run", lines.run == h.RUNS / "uniform" and lines.choice.currentText() == "Upfront line: Across", lines.choice.currentText())
    h.check("reads it again", lines.plot.view is not None and lines.plot.view.section is not None)

    h.log("=== 10 a mesh")
    from wadi2d_qgis.line_plot import LinePlot

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
    yield settled(lines)
    view = lines.plot.view
    ratio = peak_ratio(view)
    h.log(f"mesh, Across: ratio {ratio:.3f}")
    h.check("on a mesh the line stands near its record", abs(ratio - 1.0) < 0.25, ratio)
    h.widget_shot("mesh_line", lines.plot)
    tall = LinePlot()
    tall.resize(620, 760)
    tall.show_view(view, 12)
    h.widget_shot("tall", tall)

    h.log("=== 11 the panel goes with the plugin")
    folder = lines.folder
    dock.release()
    h.check("released", dock.line_panel is None)
    h.check("its files are gone", not os.path.exists(folder), folder)
