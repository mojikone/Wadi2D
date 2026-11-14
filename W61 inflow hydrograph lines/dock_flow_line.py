"""W61 through the real dock: the Boundaries table offers the flow kind with a hydrograph file, and the run takes it."""

import json


def cells(table, row):
    return table.cellWidget(row, 1), table.cellWidget(row, 2), table.cellWidget(row, 3)


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()
    b = dock.boundaries
    table = b.table
    coords = [o["coordinates"] for o in ground.outlets_data]
    # the two Bidah outlets meet in a cell, which a flow line may not share (the first run was refused for it, by
    # name): the flow line is the middle half of the second outlet
    (x0, y0), (x1, y1) = coords[1][0][:2], coords[1][-1][:2]
    middle = [[x0 + 0.25 * (x1 - x0), y0 + 0.25 * (y1 - y0)], [x0 + 0.75 * (x1 - x0), y0 + 0.75 * (y1 - y0)]]
    two = h.add_vector(h.geojson("two", [h.line(coords[0]), h.line(middle)]), "two lines", ground.crs)

    h.log("=== 1 the kind is offered with its file column")
    kinds = [b.kind.itemText(i) for i in range(b.kind.count())]
    h.check("flow is a kind", "flow" in kinds, kinds)
    h.check("a file column", table.columnCount() == 4 and table.horizontalHeaderItem(3).text() == "Hydrograph file")
    b.layer.setLayer(two)
    h.check("one row per line", table.rowCount() == 2, table.rowCount())
    b.kind.setCurrentText("free")
    kind, value, chooser = cells(table, 1)
    h.check("a free line has no file", not chooser.isEnabled())
    kind.setCurrentText("flow")
    h.check("a flow line takes a file", chooser.isEnabled())
    h.check("and no value", not value.isEnabled())

    h.log("=== 2 a run on Bidah ground at 20 m")  # a flow line with no file: tests/plugin/test_contract.py
    t = dock.terrain
    t.dem.setLayer(ground.dem)
    t.dx.setValue(20.0)
    t.domain.setLayer(ground.domain)
    dock.hydrology.rain.setValue(10.0)
    dock.hydrology.hours.setValue(0.5)
    dock.panel.duration.setValue(1.0)
    dock.panel.pixels.setChecked(False)

    h.log("=== 3 the file reaches the engine and its water enters whole")
    csv = h.RUNS / "inflow.csv"
    csv.parent.mkdir(parents=True, exist_ok=True)
    csv.write_text("minutes,flow\n0,0\n10,20\n30,20\n40,0\n", encoding="utf-8")
    chooser.setFilePath(str(csv))
    b.setCollapsed(False)
    b.resize(560, b.sizeHint().height())
    h.widget_shot("boundaries_flow", b)
    folder = h.RUNS / "flow"
    dock.panel.folder.setFilePath(str(folder))
    yield from h.run(dock)
    done = h.events(folder, "done")
    h.check("finished", done and done[-1]["code"] == 0, dock.panel.message.text())
    written = json.loads((folder / "job.json").read_text(encoding="utf-8"))["boundaries"]
    h.check("line 1 stays free", written[0]["kind"] == "free", written[0])
    h.check("line 2 is a flow line with its file", written[1]["kind"] == "flow" and written[1]["flow"]["file"] == str(csv), written[1])
    resolved = json.loads((folder / "config.resolved.json").read_text(encoding="utf-8"))["boundaries"][1]
    h.check("the engine took it", resolved["flow"]["distribution"] == "normal_depth", resolved)
    balance = done[-1]["balance"]
    volume = 20.0 * (5.0 + 20.0 + 5.0) * 60.0
    h.check("the hydrograph entered whole", abs(balance["inflow_m3"] / volume - 1.0) < 1e-5, (balance["inflow_m3"], volume))
    h.check("mass closes", abs(balance["relative_error"]) < 1e-5, balance["relative_error"])
