"""4a of his order of 2026-11-07, through the real dock: on the Block 2 hybrid (the W20 storm scenario's HMS run, at 80 m),
the run names the lines that cross a lumped inflow's cells, and the Result lines panel offers every lumped element's
inflow and outflow of record beside the lines.
"""

import json


def settled(lines):
    return lambda: lines.query is None and not lines.waiting


def scenario(h):
    ground = h.Bidah()
    dock = yield from h.open_dock()
    hills = h.BLOCK / "HEC_HMS_Block_02"
    domain = h.add_vector(h.VALIDATION / "domain.geojson", "domain block 2", ground.crs)
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    outlets = h.add_vector(h.geojson("outs", [h.line(k["coordinates"], kind="normal", value=0.008) for k in jobs["boundaries"]]), "block outlets", ground.crs)
    rings = h.add_vector(h.geojson("dams", [h.line(k["coordinates"], name=k["name"]) for k in jobs["outputs"]["lines"]]), "block dams", ground.crs)
    t, y, storm = dock.terrain, dock.hydrology, dock.storm
    t.dem.setLayer(ground.dem)
    t.domain.setLayer(domain)
    t.dx.setValue(80.0)
    y.folder.setFilePath(str(hills))
    yield lambda: y.files["basin"].count() > 0
    y.files["met"].setCurrentText("FM_100yr.met")
    storm.kind.setCurrentIndex(storm.kind.findData("hms"))
    dock.boundaries.layer.setLayer(outlets)
    dock.points.layer.setLayer(rings)
    dock.points.name.setField("name")
    dock.panel.duration.setValue(30.0)
    dock.panel.pixels.setChecked(False)
    folder = h.RUNS / "hybrid"
    dock.panel.folder.setFilePath(str(folder))

    h.log("=== 1 the run names the lines over an inflow")
    yield from h.run(dock, 2400)
    done = h.events(folder, "done")
    h.check("the hybrid ran", done and done[-1].get("code") == 0, dock.panel.message.text())
    warned = [e["message"] for e in h.events(folder, "warn") if "pond's surge" in e.get("message", "")]
    named = sorted(m.split()[1] + " " + m.split()[2] for m in warned)
    h.log(f"lines named: {named}")
    h.check("the S5 ring is named", any(m.startswith("line S5 ring crosses") for m in warned), named)
    h.check("the S11 ring is named", any(m.startswith("line S11 ring crosses") for m in warned), named)
    dams = sorted({m.split(" crosses")[0][5:] for m in warned if "ring" not in m.split(" crosses")[0]})
    h.log(f"dam lines over an inflow's cells (a finding, not a check): {dams}")

    h.log("=== 2 the panel offers the lumped elements of record")
    dock.panel.lines_button.click()
    lines = dock.line_panel
    yield settled(lines)
    labels = [lines.choice.itemText(i) for i in range(lines.choice.count())]
    lumped = [text for text in labels if text.startswith("Lumped element: ")]
    h.log(f"{len(lumped)} lumped elements listed, e.g. {lumped[:4]}")
    h.check("lumped elements are listed after the lines", lumped and labels.index(lumped[0]) > 0, labels[:3])
    h.check("S5 is among them", "Lumped element: S5" in labels, lumped)
    lines.choice.setCurrentIndex(labels.index("Lumped element: S5"))
    yield settled(lines)
    view = lines.plot.view
    h.check("the S5 view is the network's", view is not None and view.heading.startswith("Lumped element: S5"), view.heading if view else None)
    peak = max(view.charts[0].curves[0].values)
    rows = (folder / "series" / "network_S5.csv").read_text(encoding="utf-8").splitlines()
    header = rows[0].split(",")
    column = header.index("outflow_m3s")
    record = max(abs(float(r.split(",")[column])) for r in rows[1:])
    h.log(f"S5 outflow of record {record:.1f} m3/s, plotted {peak:.1f}")
    h.check("the plot holds the network's own peak", abs(peak - record) <= 0.01 * record + 0.1, (peak, record))
    h.check("its limit says why it is the number to read", "pond's surge" in view.limit, view.limit)
    h.widget_shot("lumped_S5", lines.plot)
