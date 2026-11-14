"""W74 through the real dock: the chart heading by kind on the HMS route, Add to chart over it, and the dam workbook
with a renamed sheet filled from our own run's reservoir series (pool, storage, each structure).

The run is W68's (``W68 layer groups and dock rows/dock_hms_structures.py``): Bidah 03 at 30 m on the CPU, Block 2's 200-yr
frequency storm from W68's copy of his HMS project (``hms_copy.py``: Bidah 03 reservoir with an orifice, a rating-curve
spillway and a level dam top), every subbasin rain-on-grid, a hand-back line 60 m above the dam line into the reservoir.
"""

HANDBACK = "Bidah 03 Reservoir"
SHEET = "Bidah 03 dam"
OFFSET_M = 60.0


def settled(lines):
    return lambda: lines.query is None and not lines.waiting


def scenario(h):
    import importlib.util
    import json
    import re
    import zipfile
    from pathlib import Path

    from qgis.core import QgsGeometry, QgsPointXY
    from qgis.gui import QgsMapMouseEvent
    from qgis.PyQt.QtCore import QEvent, QPoint, Qt
    from qgis.PyQt.QtWidgets import QMenu
    from qgis.utils import iface

    h.VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")  # a worktree has no venv of its own
    w68 = Path(h.SCENARIO).parents[1] / "W68 layer groups and dock rows"
    spec = importlib.util.spec_from_file_location("hms_copy", w68 / "hms_copy.py")
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
    best = max([s.intersection(domain) for s in sides], key=lambda g: g.length())
    part = max(best.asGeometryCollection(), key=lambda g: g.length()) if best.isMultipart() else best
    coords = [[p.x(), p.y()] for p in part.asPolyline()]
    handback = h.add_vector(h.geojson("handback", [h.line(coords, name=HANDBACK, element=HANDBACK)]), "hand-back", ground.crs)

    dock = yield from h.open_dock()
    hy, storm = dock.hydrology, dock.storm
    h.set_rain_job(dock, ground, "polish_hms", dx=30.0, rain=10.0, hours=1.0, sim_hours=12.0, pixels=False)
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

    folder = h.RUNS / "polish_hms"
    yield from h.run(dock, 2400)
    done = h.events(folder, "done")
    h.check("the run finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text()[:300])

    # the chart: the reservoir's heading names its kind on the HMS route (W68 found "Lumped element:")
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

    def right_click():
        event = QgsMapMouseEvent(canvas, QEvent.MouseButtonPress, QPoint(round(pixel.x()), round(pixel.y())), Qt.RightButton)
        menu = QMenu()
        canvas.contextMenuAboutToShow.emit(menu, event)
        return menu

    menu = right_click()
    texts = [a.text() for a in menu.actions()]
    h.log(f"right-click on the hand-back line: {texts}")
    wanted = [a for a in menu.actions() if a.text() == f"Hydrograph: Lumped element: {HANDBACK}"]
    h.check("the right-click offers the reservoir's hydrograph", bool(wanted), texts)
    if wanted:
        wanted[0].trigger()
        yield lambda: True
        view = lines.plot.view
        heading = view.heading if view is not None else ""
        h.log(f"heading: {heading} | note: {view.note if view else ''}")
        h.check("the heading names the kind on the HMS route", heading == f"Reservoir: {HANDBACK}.", heading)
        h.check("the reservoir's drainage area, and its tc said not available", view is not None
                and view.note.startswith("Drainage area ") and "tc not available" in view.note, view.note if view else "")  # fmt: skip
        before = len(view.charts[0].curves) if view else 0
        menu = right_click()
        adds = [a for a in menu.actions() if a.text().startswith("Add to chart: ")]
        h.log(f"add entries: {[a.text() for a in adds]}")
        h.check("the right-click also offers Add to chart for the others under it", bool(adds), [a.text() for a in menu.actions()])
        if adds:
            name = adds[0].text().split(": ", 2)[-1]
            adds[0].trigger()
            yield settled(lines)
            view = lines.plot.view
            h.check("the second element is drawn over the reservoir's chart", view is not None
                    and view.heading.startswith(f"Reservoir: {HANDBACK}. Added: ")
                    and len(view.charts[0].curves) == before + 1, (view.heading if view else "", name))  # fmt: skip
            h.widget_shot("chart_overlay", lines.plot)
        lines.clear_added()
        h.check("Clear added gives the reservoir's chart back", lines.plot.view.heading == f"Reservoir: {HANDBACK}.", lines.plot.view.heading)

    # the dam workbook: the reservoir's sheet renamed, filled from our own run's series
    dock.panel.workbook_button.click()
    dialog = dock.workbook_dialog
    dialog.runs.item(0, 0).setText("200")
    offered = [dialog.elements.item(i, 0).text() for i in range(dialog.elements.rowCount())]
    h.log(f"workbook elements offered: {offered}")
    for i in range(dialog.elements.rowCount()):
        item = dialog.elements.item(i, 0)
        mine = item.text() == "Bidah_03_Reservoir"
        item.setCheckState(Qt.Checked if mine else Qt.Unchecked)
        if mine:
            dialog.elements.item(i, 1).setText(SHEET)
    out = h.P / "dam_workbook.xlsx"
    dialog.out.setFilePath(str(out))
    dialog.write_button.click()
    yield lambda: dialog.query is None
    h.check("the workbook is written", out.is_file() and "Workbook written" in dialog.message.text(), dialog.message.text())
    if out.is_file():
        with zipfile.ZipFile(out) as book:  # QGIS's Python has no openpyxl: read the file itself
            sheets = re.findall(r'<sheet [^>]*name="([^"]+)"', book.read("xl/workbook.xml").decode("utf-8"))
            text = book.read("xl/sharedStrings.xml").decode("utf-8") if "xl/sharedStrings.xml" in book.namelist() else ""
            text += "".join(book.read(n).decode("utf-8") for n in book.namelist() if n.startswith("xl/worksheets/"))
        h.log(f"workbook sheets: {sheets}")
        h.check("the renamed sheet", SHEET in sheets and "Bidah_03_Reservoir" not in sheets, sheets)
        columns = ["Pool_200yr", "Storage_200yr", "Orifice_1_200yr", "Rating_spillway_1_200yr", "Dam_top_1_200yr"]
        h.check("pool, storage and each structure from the run", all(c in text for c in columns), [c for c in columns if c not in text])
        h.check("the sheet's summaries of the reservoir", "Peak outflow" in sheets and "Highest pool level" in sheets, sheets)
    dialog.close()
