"""D6b through the real dock on Bidah: generate, lumped by default, one subbasin in 2D, an incomplete element, the
double-rain check is engine-side (tests/engine), hand-back rows, the transmission row, the HMS switch."""

import json

from qgis.PyQt.QtCore import QPointF
from qgis.PyQt.QtGui import QColor

SIM_HOURS = 3.0
THRESHOLD_KM2 = 2.0


def done_event(h, folder):
    found = h.events(folder, "done")
    return found[-1] if found else {}


def balance(h, folder):
    return done_event(h, folder).get("balance", {})


def warnings(h, folder):
    """The run's warnings, less the edge ponding of the Bidah test domain, whose western edge holds rain-on-grid water."""
    return [e["message"] for e in h.events(folder, "warn") if "against the domain edge" not in e["message"]]


def series_volume(folder, name, column="outflow_m3s"):
    import csv

    path = folder / "series" / f"network_{name.replace(' ', '_')}.csv"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    t, q = rows[0].index("t_s"), rows[0].index(column)
    body = [(float(r[t]), float(r[q])) for r in rows[1:]]
    return sum(0.5 * (a[1] + b[1]) * (b[0] - a[0]) for a, b in zip(body, body[1:]))


def modes(table):
    return {table.item(r, 0).text(): table.cellWidget(r, 1).currentText() for r in range(table.rowCount())}


def scenario(h):
    ground = h.Bidah()
    dam = json.loads((h.VALIDATION / "jobs" / "dam_Bidah03_100yr_20.json").read_text(encoding="utf-8"))
    crests = [o for o in dam["terrain"]["objects"] if o["kind"] == "crest_line"]  # the axis and two saddle pieces
    spillway = next(o for o in dam["terrain"]["objects"] if o["kind"] == "spillway")
    longest = max(crests, key=lambda o: len(o["coordinates"]))
    crest = h.add_vector(
        h.geojson("crest", [h.line(o["coordinates"], z=o["z_constant"], name="Bidah 03" if o is longest else f"saddle {n}")
                            for n, o in enumerate(crests, 1)]),
        "crest", ground.crs,
    )  # fmt: skip
    spill = h.add_vector(
        h.geojson("spill", [h.line(spillway["coordinates"], z=spillway["z_constant"], c=2.1, l=spillway["length"])]),
        "spill", ground.crs,
    )  # fmt: skip
    cn = h.add_raster(h.BLOCK / "HEC_HMS_Block_02" / "Hydrology Data" / "CN_Include_Hill_Area.tif", "cn")
    dock = yield from h.open_dock()
    hy, box, s = dock.hydrology, dock.hydrology.basin, dock.structures

    h.set_rain_job(dock, ground, "basin_lumped", dx=20.0, rain=60.0, hours=1.0, sim_hours=SIM_HOURS, pixels=False)
    hy.cn.raster.setLayer(cn)
    s.layers["crest_line"].setLayer(crest)
    s.fields["crest_line"]["crest_z"].setField("z")
    s.layers["spillway"].setLayer(spill)
    s.fields["spillway"]["crest_z"].setField("z")
    s.fields["spillway"]["coefficient"].setField("c")
    s.fields["spillway"]["length"].setField("l")

    h.log("=== 1 generate the basin from the DEM")
    h.check("the box starts unticked and the subbasin table hidden", not box.isChecked() and not hy.table.isVisible())
    h.check("the lag choices are the engine's", [box.lag.itemData(i) for i in range(box.lag.count())] == ["nrcs", "hms_kirpich"])
    box.setChecked(True)
    h.check("the HMS folder is disabled while the basin is on", not hy.folder.isEnabled())
    box.threshold.setValue(THRESHOLD_KM2)
    box.generate_button.click()
    h.check("the button is busy", not box.generate_button.isEnabled())
    yield lambda: box.generate_button.isEnabled()
    h.log(f"summary: {box.summary.text()}")
    h.check("a basin was generated", box.model is not None, box.summary.text())
    model = box.model
    subs = [e for e in model["elements"] if e["kind"] == "subbasin"]
    reaches = [e for e in model["elements"] if e["kind"] == "reach"]
    nodes = [e for e in model["elements"] if e["kind"] in ("junction", "reservoir")]
    h.check("subbasins, reaches and junctions", len(subs) >= 3 and len(reaches) >= 1 and len(nodes) >= 2, (len(subs), len(reaches), len(nodes)))
    dam_el = next((e for e in model["elements"] if e["name"] == "Bidah 03"), None)
    h.check("the crest line is a reservoir with its rating complete", dam_el is not None and dam_el["kind"] == "reservoir" and dam_el["missing"] == [], dam_el and dam_el["missing"])
    group = h.group_of("Wadi2D basin")
    layers = [n.layer() for n in group.findLayers()] if group else []
    h.check("three basin layers loaded", len(layers) == 3, [la.name() for la in layers])
    h.check("the subbasin table shows every subbasin", hy.table.isVisible() and hy.table.rowCount() == len(subs), hy.table.rowCount())
    h.check("every subbasin lumped by default", set(modes(hy.table).values()) == {"lumped"}, modes(hy.table))
    h.check("the junction table has every junction", box.table.rowCount() == len(nodes), box.table.rowCount())
    words = [box.table.item(r, 3).text() for r in range(box.table.rowCount())]
    h.check("the route column says what happens before a run", all(words), words)
    h.check("the summary counts", f"{len(subs)} subbasins, {len(reaches)} reaches" in box.summary.text(), box.summary.text())
    extent = ground.domain.extent()
    centre = QPointF(extent.center().x(), extent.center().y())
    h.render("basin_bidah", [*layers, ground.dem], centre, 40000, size=(1200, 1000))
    h.widget_shot("hydrology_generated", hy)
    basin_dir = h.RUNS / "basin_lumped" / "wadi2d_basin"
    h.check("basin.json and basin.gpkg are inside the output folder", (basin_dir / "basin.json").is_file() and (basin_dir / "basin.gpkg").is_file())

    h.log("=== 2 run lumped by default")
    yield from h.run(dock)
    out = h.RUNS / "basin_lumped"
    done = done_event(h, out)
    h.check("the run finished", done.get("code") == 0, dock.panel.message.text())
    job = json.loads((out / "job.json").read_text(encoding="utf-8"))
    h.check("the job names basin.json and every subbasin lumped", job["hydrology"]["basin_json"].endswith("basin.json") and all(s["mode"] == "lumped" for s in job["hydrology"]["subbasins"]))
    h.check("the job records the threshold and the lag method", job["basin"] == {"stream_threshold_km2": THRESHOLD_KM2, "lag_method": "nrcs"}, job.get("basin"))
    events = h.events(out, "basin")
    h.check("one basin event in progress.jsonl", len(events) == 1 and events[0]["handbacks"] == [] and set(events[0]["lumped"]) == {s["name"] for s in subs}, events and events[0].get("handbacks"))
    h.check("no warning but the test domain's edge", warnings(h, out) == [], warnings(h, out))
    b_l = balance(h, out)
    if not b_l:
        h.check("no balance: the run did not finish", False, dock.panel.message.text()[:300])
        return
    h.check("the water enters as inflow at the junctions, and only the unassigned ground rains", 0.0 < b_l.get("rain_m3", 0) < b_l.get("inflow_m3", 0), (b_l.get("inflow_m3"), b_l.get("rain_m3")))
    h.check("mass closes", abs(b_l.get("relative_error", 1)) < 1e-6, b_l.get("relative_error"))
    series = sorted(p.name for p in (out / "series").glob("network_*.csv"))
    h.check("network series for every element", len(series) == len(model["elements"]), len(series))
    resolved = json.loads((out / "config.resolved.json").read_text(encoding="utf-8"))["hydrology"]
    h.check("the resolved job lists every subbasin and the junction inflows", len(resolved["subbasins"]) == len(subs) and len(resolved["inflows"]) >= 1, len(resolved["inflows"]))
    h.check("the junction table took the run's word", "enters the 2D grid here" in " ".join(box.table.item(r, 3).text() for r in range(box.table.rowCount())))
    h.log(f"lumped balance: {b_l}")

    h.log("=== 3 one subbasin switched to rain-on-grid")
    routes = {r["junction"]: r for r in model["routes"]}
    reach_junction = next(j for j, r in routes.items() if r["route"] == "reach")
    above = next(e["name"] for e in subs if e["downstream"] == reach_junction)
    for r in range(hy.table.rowCount()):
        if hy.table.item(r, 0).text() == above:
            hy.table.cellWidget(r, 1).setCurrentText("2d")
    dock.panel.folder.setFilePath(str(h.RUNS / "basin_2d"))
    yield from h.run(dock)
    out2 = h.RUNS / "basin_2d"
    done2 = done_event(h, out2)
    h.check("the 2D run finished", done2.get("code") == 0, dock.panel.message.text())
    ev2 = h.events(out2, "basin")[0]
    plan = next(j for j in ev2["junctions"] if j["junction"] == reach_junction)
    h.check(f"a hand-back line was built at {reach_junction} for {above}", ev2["handbacks"] == [reach_junction] and plan["handback"] and plan["two_d_sources"] == [above], (ev2["handbacks"], plan))
    job2 = json.loads((out2 / "job.json").read_text(encoding="utf-8"))
    h.check("the job says 2d for that subbasin and nothing else changed", next(s["mode"] for s in job2["hydrology"]["subbasins"] if s["name"] == above) == "2d" and "handbacks" not in job2["hydrology"])
    resolved2 = json.loads((out2 / "config.resolved.json").read_text(encoding="utf-8"))["hydrology"]
    h.check("the resolved job carries the built line", [x["element"] for x in resolved2["handbacks"]] == [reach_junction])
    b2 = balance(h, out2)
    if not b2:
        h.check("no balance: the 2D run did not finish", False, dock.panel.message.text()[:300])
        return
    # the subbasin's water, lumped: its own hydrograph in the lumped run; in 2D: the rain the grid gained
    lumped_arm = series_volume(out, above)
    grid_arm = b2["rain_m3"] - b_l["rain_m3"]
    h.check(f"the same water for {above} within 5 % (the hydrograph's tail is the rest)", abs(grid_arm - lumped_arm) < 0.05 * lumped_arm, (round(lumped_arm), round(grid_arm)))
    kept = b2["storage_end_m3"] - b_l["storage_end_m3"]
    h.check("what the arm rained crossed the line or is still on the grid", abs(b2.get("handback_m3", 0) + kept - grid_arm) < 0.03 * grid_arm, (round(b2.get("handback_m3", 0)), round(kept), round(grid_arm)))
    h.check("the whole closes to the routing defect", abs(b2.get("whole_relative_error", 1)) < 1e-2 and abs(b2["relative_error"]) < 1e-6, (b2.get("whole_relative_error"), b2["relative_error"]))
    line_file = out2 / "series" / f"handback_{reach_junction.replace(' ', '_')}.csv"
    h.check(f"{line_file.name} written", line_file.is_file())
    h.log(f"2d balance: {b2}")

    h.log("=== 4 an element lacking a parameter is refused into rain-on-grid and named")
    hy.cn.raster.setLayer(None)
    hy.cn.box.setValue(hy.cn.box.minimum())  # "No losses": no CN anywhere, so every subbasin lacks one
    box.generate_button.click()
    yield lambda: box.generate_button.isEnabled()
    h.check("generated again", box.model is not None and "Rain-on-grid for lack of a parameter" in box.summary.text(), box.summary.text()[:200])
    h.check("every row says 2d and cannot be changed", set(modes(hy.table).values()) == {"2d"} and not hy.table.cellWidget(0, 1).isEnabled(), modes(hy.table))
    h.check("the tooltip names curve_number", "curve_number" in hy.table.item(0, 0).toolTip(), hy.table.item(0, 0).toolTip())
    dock.panel.folder.setFilePath(str(h.RUNS / "basin_incomplete"))
    dock.panel.duration.setValue(1.0)
    yield from h.run(dock)
    out3 = h.RUNS / "basin_incomplete"
    warned = warnings(h, out3)
    h.check("the run finished", done_event(h, out3).get("code") == 0, dock.panel.message.text())
    h.check("the warning names the element and curve_number", any("curve_number" in w and "rain-on-grid" in w for w in warned), warned[:2])
    ev3 = (h.events(out3, "basin") or [{}])[0]
    h.check("the event lists them as incomplete and 2d", set(ev3.get("two_d", [])) == {s["name"] for s in subs} and len(ev3.get("incomplete", [])) >= len(subs), (len(ev3.get("two_d", [])), len(ev3.get("incomplete", []))))
    h.check("every reach junction got a line, chained down to the outlet", len(ev3.get("handbacks", [])) == sum(r["route"] == "reach" for r in box.model["routes"]), ev3.get("handbacks"))
    h.check("the dock shows the warning", "rain-on-grid" in dock.panel.message.text(), dock.panel.message.text()[:200])
    h.widget_shot("hydrology_incomplete", hy)

    h.log("=== 5 hand-back rows from a line layer")
    hy.handbacks.layer.setLayer(ground.lines)
    n = ground.lines.featureCount()
    h.check("one row per line", hy.handbacks.table.rowCount() == n, hy.handbacks.table.rowCount())
    combo = hy.handbacks.table.cellWidget(0, 1)
    choices = [combo.itemText(i) for i in range(combo.count())]
    h.check("the element choices are the generated reaches and junctions", set(choices) == {e["name"] for e in box.model["elements"] if e["kind"] != "subbasin"}, choices[:6])
    combo.setCurrentText(reaches[0]["name"])
    values = dock._collect()
    h.check("the values carry the lines with their elements", [f.properties["element"] for f in values["handbacks"]][0] == reaches[0]["name"], [f.properties for f in values["handbacks"]][:2])
    hy.handbacks.layer.setLayer(None)

    h.log("=== 6 the transmission loss row")
    h.check("off by default", not hy.loss.enabled.isChecked() and not hy.loss.rate.isEnabled())
    hy.loss.enabled.setChecked(True)
    hy.loss.rate.setValue(25.0)
    from wadi2d_qgis.job_builder import build_job

    hy.cn.box.setValue(80.0)
    job6 = build_job(dock._collect(), h.RUNS / "job6")
    h.check("the job has the loss on at 25 mm/h", job6.get("transmission") == {"enabled": True, "rate_mm_h": 25.0}, job6.get("transmission"))
    hy.loss.enabled.setChecked(False)
    h.check("off leaves the job without it", "transmission" not in build_job(dock._collect(), h.RUNS / "job6b"))

    h.log("=== 7 an HMS project switches the basin off, and back")
    hy.folder.setFilePath(str(h.BLOCK / "HEC_HMS_Block_02"))
    h.check("the basin box is off and disabled under an HMS project", not box.isChecked() and not box.isEnabled())
    h.check("the subbasin table shows the HMS subbasins", hy.table.rowCount() == 18, hy.table.rowCount())
    hy.folder.setFilePath("")
    h.check("the basin box is enabled again", box.isEnabled())
    box.setChecked(True)
    h.check("the generated subbasins are back in the table", hy.table.rowCount() == len(subs), hy.table.rowCount())
    h.widget_shot("hydrology_final", hy)
