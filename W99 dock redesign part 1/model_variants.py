"""Kinds of input the first scenario's model does not use, each saved and brought back in one QGIS session.

For each: fill, take the model document and the job; put the dock back to its defaults; apply the document; the
document, the job and every input file must be what they were. Loaded by ``dock_model_saved_b.py``.
"""

import shutil


def point(xy, **props):
    return {"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": list(xy)}}


def round_trip(h, mf, name, dock, shared, wait=None):
    model = dock.model
    doc = model.collect()
    out = shared / "variant"
    job = mf.built(dock, out)
    files = mf.input_files(out)
    model.reset()
    h.check(f"{name}: the dock went back to its defaults", model.collect()["sections"] != doc["sections"])
    words = model.apply(doc)
    if wait is not None:
        yield wait
    h.check(f"{name}: nothing is reported as lost", words == [], words[:4])
    now = model.collect()["sections"]
    h.check(f"{name}: the model is the same", now == doc["sections"], mf.differences(doc["sections"], now)[:6])
    again = mf.built(dock, out)
    h.check(f"{name}: the job is the same", again == job, mf.differences(job, again)[:6])
    h.check(f"{name}: the input files are the same", mf.input_files(out) == files)
    return job


def round_trips(h, mf, dock, layers, shared):
    from qgis.core import QgsProject

    crs = layers["terrain"].crs()
    box = layers["domain bidah"].extent()
    cx, cy = box.center().x(), box.center().y()
    t, hy, s, b, st = dock.terrain, dock.hydrology, dock.storm, dock.boundaries, dock.structures

    def base():
        dock.model.reset()
        t.dem.setLayer(layers["terrain"])
        t.domain.setLayer(layers["domain bidah"])
        dock.panel.folder.setFilePath(str(shared / "runs" / "variant"))

    h.log("--- rain gauges from a point layer and one typed in, inverse distance")
    base()
    records = []
    for name, mm in (("west", 10.0), ("east", 2.5)):
        path = h.DATA / f"w99_{name}.csv"
        path.write_text("time,rain_mm\n15,%s\n30,%s\n" % (mm, mm), encoding="utf-8")
        records.append(str(path))
    gauges = h.add_vector(
        h.geojson("w99_gauges", [point((cx - 900.0, cy), name="west"), point((cx + 900.0, cy), name="east")]), "w99 gauges", crs
    )
    s.kind.setCurrentIndex(s.kind.findData("gauges"))
    s.gauge_table.layer.setLayer(gauges)
    s.gauge_table.name_field.setField("name")
    s.gauge_table.set_row(0, file=records[0], series="rain_mm")
    s.gauge_table.set_row(1, file=records[1])
    s.gauge_table.add_row("rain")
    s.gauge_table.set_row(2, name="typed", file=records[1], x=cx, y=cy + 400.0)
    s.gauge_method.setCurrentIndex(s.gauge_method.findData("inverse_distance"))
    s.gauge_radius.setValue(5000.0)
    s.gauge_start.setText("2021-10-04 00:00")
    job = yield from round_trip(h, mf, "rain gauges", dock, shared)
    h.check("rain gauges: three gauges reach the job", len(job["storm"]["gauges"]["gauges"]) == 3 and job["storm"]["gauges"].get("search_radius_m") == 5000.0, job["storm"])

    h.log("--- a hyetograph table, a flow line with its file, at rest, to the left")
    base()
    flow = h.DATA / "w99_inflow.csv"
    flow.write_text("minutes,m3s\n0,0\n30,40\n90,0\n", encoding="utf-8")
    s.kind.setCurrentIndex(s.kind.findData("single"))
    s.single.setCurrentIndex(s.single.findData("hyetograph"))
    s.hyetograph.set_rows([(15.0, 4.0), (30.0, 11.5), (45.0, 2.0)])
    b.layer.setLayer(layers["mixed outlets"])
    b.table.cellWidget(1, 1).setCurrentText("flow")
    b.table.cellWidget(1, 3).setFilePath(str(flow))
    b.table.cellWidget(1, 4).setChecked(False)
    side = b.table.cellWidget(1, 5)
    side.setCurrentIndex(side.findData("left"))
    job = yield from round_trip(h, mf, "hyetograph and flow line", dock, shared)
    h.check("hyetograph and flow line: the flow line is in the job", job["boundaries"][1].get("flow", {}).get("direction") == "left", job["boundaries"][1])

    h.log("--- gridded rain from a folder, a given reduction factor")
    base()
    grids = h.DATA / "w99_grids"
    grids.mkdir(exist_ok=True)
    s.kind.setCurrentIndex(s.kind.findData("gridded"))
    s.is_folder.setCurrentIndex(1)
    s.rain_file.setFilePath(str(grids))
    s.period.setValue(10.0)
    s.stamp.setCurrentIndex(1)
    s.start.setText("2021-10-03 06:00")
    s.arf_mode.setCurrentIndex(s.arf_mode.findData("given"))
    s.arf_factor.setValue(0.7)
    job = yield from round_trip(h, mf, "gridded rain", dock, shared)
    h.check("gridded rain: the factor and the start reach the job", job["storm"].get("arf_factor") == 0.7 and job["storm"].get("rain_start") == "2021-10-03 06:00", job["storm"])

    h.log("--- corridors, an embankment with numbers, a breach, no mesh")
    base()
    dock.mesh.corridors.setChecked(True)
    dock.mesh.corridor_layer.setLayer(layers["w99 refinement"])
    dock.mesh.corridor_cell_min.setValue(10.0)
    dock.mesh.corridor_outside.setValue(2)
    st.layers["embankment"].setLayer(layers["w99 crests"])
    st.shaped["embankment"].fields["crest_z"].setField("crest_z")
    st.shaped["embankment"].numbers["width"].box.setValue(6.5)
    st.shaped["embankment"].fields["name"].setField("name")
    st.shaped["embankment"].taper.setValue(12.0)
    st.breaches.add()
    row = st.breaches.rows[0]
    row.bottom_z, row.width_m, row.formation_min, row.value = 88.0, 30.0, 45.0, 101.5
    st.breaches.fill()
    job = yield from round_trip(h, mf, "corridors, embankment, breach", dock, shared)
    h.check("corridors, embankment, breach: all three reach the job", "strips" in job and "breaches" in job and job["terrain"]["objects"][0]["kind"] == "embankment", list(job))

    h.log("--- an HMS project: files, modes, Muskingum numbers, the lumped network's entry")
    base()
    hms = h.P / "hms"  # his project is read-only: the three files the dock reads, copied
    hms.mkdir(exist_ok=True)
    for name in ("Basin_3.basin", "FM_200yr.met", "Control_1.control"):
        shutil.copy2(h.BLOCK / "HEC_HMS_Block_02" / name, hms / name)
    hy.folder.setFilePath(str(hms))
    yield lambda: hy.files["basin"].count() > 0
    hy.files["basin"].setCurrentText("Basin_3.basin")
    hy.files["met"].setCurrentText("FM_200yr.met")
    hy.files["control"].setCurrentText("Control_1.control")
    yield lambda: hy.table.rowCount() > 0
    for r in range(0, hy.table.rowCount(), 3):
        hy.table.cellWidget(r, 1).setCurrentText("2d")
    hy.lumped_entry.setCurrentIndex(hy.lumped_entry.findData("network"))
    hy.exclude.setChecked(True)
    hy.routing.setCurrentIndex(hy.routing.findData("muskingum"))
    yield lambda: hy.muskingum.table.rowCount() > 0
    hy.muskingum.table.item(0, 2).setText("1.25")
    hy.muskingum.table.item(0, 3).setText("0.2")
    hy.muskingum.velocity.setValue(1.8)
    s.kind.setCurrentIndex(s.kind.findData("hms"))
    job = yield from round_trip(h, mf, "HMS project", dock, shared)
    values = dock._collect()
    modes = values["hms"]["modes"]
    h.check("HMS project: the modes came back", sum(1 for m in modes.values() if m == "2d") == len(range(0, len(modes), 3)), modes)
    h.check("HMS project: the typed K and X are in the job", job["hydrology"].get("muskingum", [{}])[0].get("k_hours") == 1.25, job["hydrology"].get("muskingum", [])[:1])
    h.check("HMS project: the storm is the project's", "storm" not in job and s.kind.currentData() == "hms", s.kind.currentData())
    dock.model.reset()
    QgsProject.instance().removeMapLayer(gauges.id())


