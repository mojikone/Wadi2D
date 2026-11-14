"""W68 through the real dock: an HMS reservoir with W59's outflow structures runs, the layer tree's pattern, the dam
workbook dialog, and W64's right-click chart under the pan tool on the real run.

Bidah 03 at 30 m on the CPU, Block 2's 200-yr frequency storm from a copy of his HMS project (``hms_copy.py``: the
Bidah 03 reservoir routes by an orifice, a rating-curve spillway and a level dam top in place of its Modified Puls
curve), every subbasin rain-on-grid, a hand-back line 60 m above the dam line into the reservoir: the 2D flood leaves
the grid there and the reservoir routes it by its structures during the run.
"""

HANDBACK = "Bidah 03 Reservoir"
OFFSET_M = 60.0


def settled(lines):
    return lambda: lines.query is None and not lines.waiting


def scenario(h):
    import csv
    import importlib.util
    import json
    from pathlib import Path

    from qgis.core import QgsGeometry, QgsPointXY, QgsProject
    from qgis.gui import QgsMapMouseEvent
    from qgis.PyQt.QtCore import QEvent, QPoint, Qt
    from qgis.PyQt.QtWidgets import QMenu
    from qgis.utils import iface

    h.VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")  # a worktree has no venv of its own
    here = Path(h.SCENARIO).parent
    spec = importlib.util.spec_from_file_location("hms_copy", here / "hms_copy.py")
    copy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(copy)
    hms = copy.make(h.P / "hms")
    h.TOTAL_LIMIT = 3000.0

    ground = h.Bidah()
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    dam = next(k["coordinates"] for k in jobs["outputs"]["lines"] if k["name"] == "Bidah 03")
    domain = QgsGeometry.unaryUnion([f.geometry() for f in ground.domain.getFeatures()])
    axis = QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in dam])
    sides = [axis.offsetCurve(d, 8, QgsGeometry.JoinStyleRound, 2.0) for d in (OFFSET_M, -OFFSET_M)]
    inside = [s.intersection(domain) for s in sides]
    best = max(inside, key=lambda g: g.length())
    part = max(best.asGeometryCollection(), key=lambda g: g.length()) if best.isMultipart() else best
    coords = [[p.x(), p.y()] for p in part.asPolyline()]
    h.log(f"hand-back line {part.length():.0f} m inside the domain")
    handback = h.add_vector(h.geojson("handback", [h.line(coords, name=HANDBACK, element=HANDBACK)]), "hand-back", ground.crs)

    dock = yield from h.open_dock()
    hy, storm = dock.hydrology, dock.storm
    h.set_rain_job(dock, ground, "structures_hms", dx=30.0, rain=10.0, hours=1.0, sim_hours=12.0, pixels=False)
    dock.points.layer.setLayer(ground.lines)
    dock.points.name.setField("name")
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    hy.folder.setFilePath(str(hms))
    yield lambda: hy.files["basin"].count() > 0
    hy.files["basin"].setCurrentText("Basin_3.basin")
    hy.files["met"].setCurrentText("FM_200yr.met")
    hy.files["control"].setCurrentText("Control_1.control")
    storm.kind.setCurrentIndex(storm.kind.findData("hms"))
    yield lambda: hy.table.rowCount() > 0
    for r in range(hy.table.rowCount()):
        hy.table.cellWidget(r, 1).setCurrentText("2d")
    hy.handbacks.layer.setLayer(handback)
    yield lambda: hy.handbacks.table.rowCount() == 1
    chosen = hy.handbacks.rows[0].element if hy.handbacks.rows else None
    h.check("the hand-back line enters the reservoir", chosen == HANDBACK, chosen)

    folder = h.RUNS / "structures_hms"
    yield from h.run(dock, 2400)
    done = h.events(folder, "done")
    h.check("the run finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text()[:300])
    series = folder / "series" / "network_Bidah_03_Reservoir.csv"
    h.check("the reservoir's series is written", series.is_file(), sorted(p.name for p in (folder / "series").glob("network_*")))
    if series.is_file():
        with series.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        names = list(rows[0])
        h.log(f"reservoir columns: {names}")
        plain = {"t_s", "inflow_m3s", "outflow_m3s", "branched_m3s", "pool_m", "storage_m3", "rain_mm", "excess_mm"}
        structures = [n for n in names if n not in plain and n.endswith("_m3s")]
        h.check("each structure's flow is a column", structures == ["orifice_1_m3s", "rating_spillway_1_m3s", "dam_top_1_m3s"], names)
        inflow = max(float(r["inflow_m3s"]) for r in rows)
        outflow = max(float(r["outflow_m3s"]) for r in rows)
        pool = max(float(r["pool_m"]) for r in rows)
        orifice = max(float(r["orifice_1_m3s"]) for r in rows) if "orifice_1_m3s" in names else 0.0
        h.log(f"reservoir: peak in {inflow:.1f}, out {outflow:.1f} m3/s, highest pool {pool:.2f} m, orifice {orifice:.2f}")
        h.check("the 2D flood reaches the reservoir", inflow > 1.0, inflow)
        h.check("the structures attenuate it", 0.0 < outflow < inflow, (inflow, outflow))
        h.check("below the spillway the orifice carries it all", pool < 100.0 and abs(orifice - outflow) < 1e-6, (pool, orifice, outflow))
        h.check("the pool rises above its start", pool > 84.70, pool)

    # the layer tree: one group per model, its results and its inputs
    from wadi2d_qgis import layer_groups as g

    root = QgsProject.instance().layerTreeRoot()
    top = g.find_model("structures_hms")
    h.check("one group for the model", top is not None and top.name() == g.model_title("structures_hms"))
    if top is not None:
        names = [c.name() for c in top.children()]
        h.check("its results on top, its inputs below", names == [g.results_title("structures_hms"), g.INPUTS], names)
        inputs = [c.name() for c in top.children()[-1].children()]
        h.check("the inputs' fixed pattern", inputs == list(g.INPUT_GROUPS), inputs)
        results = [c.name() for c in top.children()[0].children()]
        h.check("a run with no pixel maps: its setup, then its cell maps", results[:2] == [g.SETUP, "max_depth"], results)
    h.check("the user's own layers stay at the root", root.findLayer(handback.id()).parent() is root)

    # the result lines panel, and the right-click on the map under the pan tool (W64)
    iface.actionPan().trigger()
    dock.panel.lines_button.click()
    lines = dock.line_panel
    yield settled(lines)
    labels = [lines.choice.itemText(i) for i in range(lines.choice.count())]
    h.log(f"panel: {labels[:12]}")
    canvas = iface.mapCanvas()
    canvas.setExtent(part.boundingBox().buffered(400.0))
    canvas.refresh()
    yield lambda: True
    middle = part.interpolate(part.length() / 2.0).asPoint()
    pixel = canvas.getCoordinateTransform().transform(middle)
    event = QgsMapMouseEvent(canvas, QEvent.MouseButtonPress, QPoint(round(pixel.x()), round(pixel.y())), Qt.RightButton)
    menu = QMenu()
    canvas.contextMenuAboutToShow.emit(menu, event)
    texts = [a.text() for a in menu.actions()]
    h.log(f"right-click on the hand-back line: {texts}")
    wanted = [a for a in menu.actions() if HANDBACK in a.text()]
    h.check("the pan tool is the map tool", canvas.mapTool() is not None and "pan" in type(canvas.mapTool()).__name__.lower(), type(canvas.mapTool()).__name__)
    h.check("the right-click offers the reservoir's hydrograph", bool(wanted), texts)
    if wanted:
        wanted[0].trigger()
        yield lambda: True
        heading = lines.plot.view.heading if lines.plot.view is not None else ""
        h.check("the reservoir's chart opens in the panel", lines.choice.currentText() == f"Lumped element: {HANDBACK}" and HANDBACK in heading, heading)
        h.widget_shot("reservoir_chart", lines.plot)

    # the dam workbook dialog, the run as its 200-yr period
    dock.panel.workbook_button.click()
    dialog = dock.workbook_dialog
    h.check("the dialog opens on the last run", dialog is not None and dialog.rows() == [("", str(folder))], dialog.rows() if dialog else None)
    dialog.runs.item(0, 0).setText("200")
    found = [dialog.elements.item(i).text() for i in range(dialog.elements.count())]
    h.log(f"workbook elements offered: {found}")
    for i in range(dialog.elements.count()):
        item = dialog.elements.item(i)
        item.setCheckState(Qt.Checked if item.text() == "Bidah_03_Reservoir" else Qt.Unchecked)
    out = h.P / "dam_workbook.xlsx"
    dialog.out.setFilePath(str(out))
    dialog.write_button.click()
    yield lambda: dialog.query is None
    h.check("the workbook is written", out.is_file() and "Workbook written" in dialog.message.text(), dialog.message.text())
    if out.is_file():
        import re
        import zipfile

        with zipfile.ZipFile(out) as book:  # QGIS's Python has no openpyxl: the sheet names from the file itself
            sheets = re.findall(r'<sheet [^>]*name="([^"]+)"', book.read("xl/workbook.xml").decode("utf-8"))
        h.log(f"workbook sheets: {sheets}")
        h.check("its target sheet and the dam's sheet", "200-year" in sheets and any("Bidah" in s for s in sheets), sheets)
    dialog.close()
