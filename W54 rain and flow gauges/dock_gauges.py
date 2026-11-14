"""W54 through the real dock: two rain gauges and an observed flow on Bidah 03 at 30 m, as a user sets them up.

Two synthetic gauges 5.5 km apart, the western one four times the eastern one's rain, both written with dates; an
observed triangle hydrograph at the Bidah 03 dam line. Run once by nearest gauge and once by inverse distance squared:
the same job but for the method, so the two answers must differ at the line, and each run's rain must equal what its
own gauge shares put on the cells.
"""

import json

from qgis.utils import iface

WEST, EAST = (433000.0, 2725500.0), (438500.0, 2725500.0)
"""Thiessen's bisector stands at x 435,750 m, across the middle of the Bidah domain."""
WEST_MM, EAST_MM = 10.0, 2.5
"""Depth in each 15-minute period, for one hour: 40 and 10 mm."""
LINE = "Bidah 03"
START = "2021-10-04 00:00"


def point(xy, name):
    return {"type": "Feature", "properties": {"name": name}, "geometry": {"type": "Point", "coordinates": list(xy)}}


def write_record(h, name, mm):
    path = h.DATA / f"{name}.csv"
    rows = "".join(f"2021-10-04 00:{m:02d},{mm}\n" for m in (15, 30, 45)) + f"2021-10-04 01:00,{mm}\n"
    path.write_text("time,rain_mm\n" + rows, encoding="utf-8")
    return str(path)


def write_observed(h):
    path = h.DATA / "observed_flow.csv"
    rows = []
    for k in range(0, 37):  # every 5 minutes for 3 h, a triangle peaking at 60 m3/s at 01:30
        minutes = 5 * k
        flow = max(0.0, 60.0 * (1.0 - abs(minutes - 90.0) / 60.0))
        rows.append(f"2021-10-04 {minutes // 60:02d}:{minutes % 60:02d},{flow:.2f}\n")
    path.write_text("time,flow_m3s\n" + "".join(rows), encoding="utf-8")
    return str(path)


def settled(lines):
    return lambda: lines.query is None and not lines.waiting


def peak(h, folder):
    rows = (folder / "series" / "line_Bidah_03.csv").read_text().splitlines()[1:]
    return max(abs(float(r.split(",")[1])) for r in rows)


def rain_check(h, folder, name):
    """The run's rain volume against its own gauge shares of the rained area: no losses on this job."""
    gauges = json.loads((folder / "rain_gauges.json").read_text(encoding="utf-8"))
    done = h.events(folder, "done")[-1]
    totals = gauges["gauges"]
    mean_mm = sum(gauges["cell_shares"][g] * totals[g] for g in totals)
    h.log(f"{name}: shares {gauges['cell_shares']}, totals {totals}, mean {mean_mm:.3f} mm, rain {done['balance']['rain_m3']:.1f} m3")
    return mean_mm, done["balance"]["rain_m3"]


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()
    panel, gauges, storm = dock.panel, dock.gauges, dock.storm
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    dam = next(k for k in jobs["outputs"]["lines"] if k["name"] == LINE)
    design = h.add_vector(h.geojson("design", [h.line(dam["coordinates"], name=LINE)]), "result line", ground.crs)
    points = h.add_vector(h.geojson("gauges", [point(WEST, "West"), point(EAST, "East")]), "rain gauges", ground.crs)
    west, east, observed = write_record(h, "west", WEST_MM), write_record(h, "east", EAST_MM), write_observed(h)

    h.log("=== 1 the section and its table")
    h.check("gauges come after the results points", dock.sections.index(gauges) == dock.sections.index(dock.points) + 1)
    h.check("the heading", gauges.title() == "7b. Gauges (optional)", gauges.title())
    h.check("the storm offers the rain gauges", storm.kind.findData("gauges") >= 0)
    h.check("an empty table", gauges.table.rowCount() == 0)
    gauges.layer.setLayer(points)
    gauges.name_field.setField("name")
    h.check("each point is a rain gauge row", [(r.name, r.kind) for r in gauges.rows] == [("West", "rain"), ("East", "rain")], [(r.name, r.kind) for r in gauges.rows])
    h.check("at its point", abs(gauges.rows[0].x - WEST[0]) < 0.01 and abs(gauges.rows[1].y - EAST[1]) < 0.01, (gauges.rows[0].x, gauges.rows[0].y))
    h.check("the table shows the position", gauges.table.item(0, 4).text() == "433000.0, 2725500.0", gauges.table.item(0, 4).text())
    flow = gauges.add_row("flow")
    h.check("a flow gauge row typed by hand", gauges.table.rowCount() == 3 and flow.kind == "flow")
    gauges.table.item(2, 0).setText("Dam gauge")
    gauges.table.item(2, 4).setText(LINE)
    h.check("typed name and line reach the row", (flow.name, flow.at) == ("Dam gauge", LINE), (flow.name, flow.at))
    gauges.start.setText(START)
    gauges.setCollapsed(False)
    h.widget_shot("gauges_table", gauges)

    h.log("=== 2 what stops a run")
    h.set_rain_job(dock, ground, "missing", dx=30.0, sim_hours=3.0, pixels=False)
    dock.points.layer.setLayer(design)
    dock.points.name.setField("name")
    storm.kind.setCurrentIndex(storm.kind.findData("gauges"))
    panel.run_button.click()
    text = panel.message.text()
    h.check("a gauge with no record is refused in words", "Gauge West: choose its record" in text, text)
    h.check("no run started", dock.run is None)
    gauges.set_row(0, file=west)
    gauges.set_row(1, file=east)
    gauges.set_row(2, file=observed)
    h.check("the record shows in the table", gauges.table.cellWidget(0, 2).filePath() == west)

    results = {}
    for method, folder_name in (("thiessen", "thiessen"), ("inverse_distance", "inverse_distance")):
        h.log(f"=== 3 a run by {method}")
        gauges.method.setCurrentIndex(gauges.method.findData(method))
        h.check(f"{method}: the radius only for inverse distance", gauges.radius.isEnabled() == (method == "inverse_distance"))
        panel.folder.setFilePath(str(h.RUNS / folder_name))
        yield from h.run(dock, limit=1500)
        folder = h.RUNS / folder_name
        done = h.events(folder, "done")
        h.check(f"{method}: finished", bool(done) and done[-1]["code"] == 0, panel.message.text())
        job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        h.check(f"{method}: the job's storm is the gauges", job["storm"]["kind"] == "gauges" and job["storm"]["gauges"]["method"] == method, job["storm"].get("kind"))
        h.check(f"{method}: the run starts at the time typed", job["storm"].get("rain_start") == START, job["storm"].get("rain_start"))
        h.check(f"{method}: the observed record names the line", job["outputs"]["observed"][0]["target"] == LINE and job["outputs"]["observed"][0]["compare"] == "line", job["outputs"].get("observed"))
        mean_mm, rain_m3 = rain_check(h, folder, method)
        area = rain_m3 / (mean_mm / 1000.0)
        results[method] = {"peak": peak(h, folder), "rain_m3": rain_m3, "mean_mm": mean_mm, "area_m2": area}
        stats = json.loads((folder / "observed" / "statistics.json").read_text(encoding="utf-8"))
        h.check(f"{method}: observed compared after the run", len(stats["records"]) == 1 and not stats["failed"], stats.get("failed"))
        results[method]["stats"] = {k: stats["records"][0][k] for k in ("nse", "rsr", "pbias_percent", "peak_ratio", "observed_peak", "simulated_peak")}
        h.log(f"{method}: {results[method]}")

    a, b = results["thiessen"], results["inverse_distance"]
    h.check("the rained area is one area under both methods", abs(a["area_m2"] - b["area_m2"]) < 1e-4 * a["area_m2"], (a["area_m2"], b["area_m2"]))
    h.check("the rained area is the domain's, about 28.8 km2", 27.0e6 < a["area_m2"] < 29.5e6, a["area_m2"])
    h.check("the two methods differ at the dam line", abs(a["peak"] - b["peak"]) > 0.02 * a["peak"], (a["peak"], b["peak"]))
    (h.P / "methods.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    h.log("=== 4 the observed flow in Result lines, on the time slider")
    panel.lines_button.click()
    lines = dock.line_panel
    yield settled(lines)
    names = [lines.choice.itemText(i) for i in range(lines.choice.count())]
    index = names.index(f"Upfront line: {LINE}")
    lines.choice.setCurrentIndex(index)
    yield settled(lines)
    view = lines.plot.view
    sources = [c.source for c in view.charts[0].curves]
    h.check("the observed flow is drawn with the computed one", "observed" in sources and "upfront" in sources, sources)
    seen = next(c for c in view.charts[0].curves if c.source == "observed")
    h.check("drawn distinctly: dashed, with a dot per value", seen.dashed and seen.markers, seen.label)
    h.check("labelled as observed", seen.label == "Observed: Dam gauge", seen.label)
    h.check("the agreement is stated", "Nash-Sutcliffe" in view.agreement and "bias" in view.agreement, view.agreement)
    h.check("its peak is the record's", abs(max(seen.values) - 60.0) < 0.01, max(seen.values))
    lines.slider.setValue(lines.slider.maximum() // 2)
    from wadi2d_qgis.line_view import readout

    said = readout(view, lines.plot.frame)
    h.check("the readout names the observed value at the frame", "(observed)" in said, said)
    h.widget_shot("observed_on_line", lines.plot)
    iface.mapCanvas().refresh()
