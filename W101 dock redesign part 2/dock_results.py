"""W101 item 6 through the real dock: the results page. Two Bidah runs, the second with twice the rain; the page of
the second lists its elements of record by kind, design lines first, searched and pinned (the pin saved in the
project), a row opening the hydrograph chart on that element; the two runs compared side by side, on one chart, and
into Excel; the map tools on the page; Open run on the start page leading to it.
"""

import json
from pathlib import Path


def scenario(h):
    import importlib.util

    from qgis.core import QgsProject
    from qgis.PyQt.QtCore import Qt

    spec = importlib.util.spec_from_file_location("w101_help", Path(h.SCENARIO).parent / "w101_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    ground = h.Bidah()
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    lines = [h.line(k["coordinates"], name=k["name"], drainage_area_km2=20.97 if k["name"] == "Bidah 03" else None) for k in jobs["outputs"]["lines"]]
    design = h.add_vector(h.geojson("w101_design", lines), "w101 design lines", ground.crs)
    dock = yield from h.open_dock()
    from wadi2d_qgis.results_links import PINS, SCOPE
    from wadi2d_qgis.results_rows import ALL, DESIGN

    page, links, panel = dock.results_page, dock.results_links, dock.panel

    def design_lines():
        dock.points.layer.setLayer(design)
        dock.points.name.setField("name")
        dock.points.area.setField("drainage_area_km2")

    def run(folder, rain):
        h.set_rain_job(dock, ground, folder, dx=30.0, rain=rain, hours=0.5, sim_hours=1.0, pixels=False)
        design_lines()
        dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
        yield from h.run(dock)
        done = h.events(dock.results_dir, "done")
        h.check(f"run {dock.results_dir.name} finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text())

    def listed():
        yield lambda: links.query is None and page.words.text() and not page.words.text().startswith("Reading")

    h.log("=== 1 the map tools left Run for the results page")
    tools = (panel.map_button, panel.frames_button, panel.pixel_frames_button, panel.window_button, panel.lines_button, panel.workbook_button)
    h.check("every map tool on the results page", all(page.isAncestorOf(b) for b in tools))
    h.check("none left in the Run card", not any(panel.isAncestorOf(b) for b in tools))
    h.check("Run has the Results button, off before a run", panel.isAncestorOf(panel.results_button) and not panel.results_button.isEnabled())

    h.log("=== 2 two runs; the page of the second")
    yield from run("results_run", 10.0)
    first = dock.results_dir
    yield from run("results_run", 20.0)
    second = dock.results_dir
    h.check("the second beside the first", second.parent == first.parent and second != first, (first, second))
    h.check("Results on", panel.results_button.isEnabled())
    panel.results_button.click()
    yield from listed()
    h.check("the results page shown", dock.pages.currentWidget() is page and second.name in page.title.text(), page.title.text())
    h.check("design lines first, by his rule", page.kind.currentData() == DESIGN and [r.name for r in links.shown] == ["Bidah 03"], ([r.name for r in links.shown], page.kind.currentData()))
    bidah = links.shown[0]
    h.check("its peak, time, volume", bidah.peak and bidah.peak > 0.0 and bidah.time_h is not None and bidah.volume_mm3 > 0.0, (bidah.peak, bidah.time_h, bidah.volume_mm3))
    h.check("the table says them", page.table.item(0, 1).text() == "Bidah 03" and page.table.item(0, 3).text() == f"{bidah.peak:,.1f}")
    page.kind.setCurrentIndex(page.kind.findData(ALL))
    total = len(links.shown)
    h.check("every element", total == len(links.rows) and total >= len(lines), (total, len(lines)))
    page.search.setText("bidah")
    h.check("the search by name", all("bidah" in r.name.lower() for r in links.shown) and len(links.shown) < total, [r.name for r in links.shown])
    page.search.setText("")

    h.log("=== 3 a pin, first whatever the filter, saved with the project")
    other = next(r for r in links.rows if r.kind != DESIGN)
    page.kind.setCurrentIndex(page.kind.findData(DESIGN))
    page.kind.setCurrentIndex(page.kind.findData(ALL))
    row = [r.key for r in links.shown].index(other.key)
    page.table.item(row, 0).setCheckState(Qt.Checked)
    page.kind.setCurrentIndex(page.kind.findData(DESIGN))
    h.check("pinned first under the design filter", [r.key for r in links.shown] == [other.key, bidah.key], [r.name for r in links.shown])
    path = h.RUNS / "results_pins.qgz"
    QgsProject.instance().write(str(path))
    again = QgsProject()
    again.read(str(path))
    saved, _ok = again.readListEntry(SCOPE, PINS.format(model=links._model()))
    h.check("the pin in the project file", list(saved) == [other.key], list(saved))
    body = page.widget()
    h.check("the page as wide as the dock, or its least width", body.width() == max(page.viewport().width(), body.minimumSizeHint().width()) and body.minimumSizeHint().width() < 320, (page.width(), body.width(), body.minimumSizeHint().width()))
    w.big_shot(h, dock, "results_page")

    h.log("=== 4 a row opens the hydrograph chart on that element")
    page.table.cellClicked.emit(1, 1)
    yield lambda: dock.line_panel is not None and dock.line_panel.query is None and dock.line_panel.choice.count() > 0
    h.check("the chart on Bidah 03", dock.line_panel.choice.currentText() == bidah.entry.label, dock.line_panel.choice.currentText())
    h.check("on this run", dock.line_panel.run == second)

    h.log("=== 5 the two runs compared")
    names = [page.runs.item(i).text() for i in range(page.runs.count())]
    h.check("the runs beside it offered, this one ticked", names[0] == second.name and first.name in names and page.runs.item(0).checkState() == Qt.Checked, names)
    page.runs.item(names.index(first.name)).setCheckState(Qt.Checked)
    page.compare_button.click()
    yield lambda: links.query is None and page.export_button.isEnabled()
    h.log(f"compared: {page.compare_words.text()}")
    header = [page.compare_table.horizontalHeaderItem(c).text() for c in range(page.compare_table.columnCount())]
    h.check("four numbers a run, side by side", len(header) == 2 + 4 * 2 and header[2] == f"{second.name}: Peak, m3/s" and header[6] == f"{first.name}: Peak, m3/s", header)
    table = links.comparison.table()
    by_name = {line[0]: line for line in table}
    h.check("the elements shown above, pinned first", [line[0] for line in table] == [other.name, "Bidah 03"], [line[0] for line in table])
    h.check("twice the rain, a higher peak", by_name["Bidah 03"][2] > by_name["Bidah 03"][6], (by_name["Bidah 03"][2], by_name["Bidah 03"][6]))
    page.compare_table.cellClicked.emit(1, 0)
    view = page.plot.view
    h.check("both runs on one chart", view is not None and len(view.charts[0].curves) == 2, None if view is None else [c.label for c in view.charts[0].curves])
    written = links.export_to(h.RUNS / "compare_runs.xlsx")
    from openpyxl import load_workbook

    sheet = load_workbook(written).active
    h.check("the table in Excel", written.suffix == ".xlsx" and sheet.cell(1, 3).value == header[2] and sheet.cell(3, 1).value == "Bidah 03", (str(written), sheet.cell(1, 3).value))
    w.big_shot(h, dock, "results_compare")

    h.log("=== 6 back to the model; Open run on the start page leads to the results")
    page.back_button.click()
    h.check("Model takes the sections back", dock.pages.currentIndex() == 1)
    dock.types.back()
    dock.start_page.run_folder.setFilePath(str(first))
    dock.start_page.open_run_button.click()
    yield from listed()
    h.check("Open run opens the run's results", dock.pages.currentWidget() is page and first.name in page.title.text(), page.title.text())
    doc = dock.model.collect()
    h.check("the page is never saved: a model opens on its sections", doc.get("types", doc).get("page", "model") != "results", doc.get("types"))
