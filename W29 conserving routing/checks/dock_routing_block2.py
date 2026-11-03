"""The reach routing option through the real dock on Block 2's HMS project: the combo holds the engine's two schemes
with HMS-faithful first, the default run writes 'hms' into job.json and the engine resolves it so, the conserving run
carries 'conserving' into job.json, config.resolved.json and the reach series, which differ from the HMS run's on the
same headwater inflows and never gain volume. The dam peaks of both runs are logged and written beside the log, not asserted.
"""

import csv
import json

DX = 40.0
DAMS = ("Faydh 01", "Bidah 03", "R5A", "R2A", "Z4C")
REACHES = tuple(f"R{n}" for n in range(1, 9))
HMS_SCHEME, CONSERVING_SCHEME = "hms", "conserving"


def done_event(h, folder):
    found = h.events(folder, "done")
    return found[-1] if found else {}


def series(folder, name):
    """t, inflow, outflow of a network element's series file."""
    path = folder / "series" / f"network_{name.replace(' ', '_')}.csv"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    head = rows[0]
    t, q_in, q_out = head.index("t_s"), head.index("inflow_m3s"), head.index("outflow_m3s")
    body = [(float(r[t]), float(r[q_in]), float(r[q_out])) for r in rows[1:]]
    return [b[0] for b in body], [b[1] for b in body], [b[2] for b in body]


def trapezoid(t, q):
    return sum(0.5 * (a + b) * (t1 - t0) for (t0, a), (t1, b) in zip(zip(t, q, strict=True), zip(t[1:], q[1:], strict=True), strict=False))


def peak(t, q):
    k = max(range(len(q)), key=lambda i: q[i])
    return {"peak_m3s": round(q[k], 1), "at_h": round(t[k] / 3600.0, 2)}


def resolved_scheme(folder):
    return json.loads((folder / "config.resolved.json").read_text(encoding="utf-8"))["hydrology"]["reach_routing"]


def scenario(h):
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    dem = h.add_raster(h.BLOCK / "Terrain" / "GGC_2_MERGE_HDSM_5.tif", "terrain")
    crs = dem.crs()
    from qgis.core import QgsProject

    QgsProject.instance().setCrs(crs)
    block = h.add_vector(h.VALIDATION / "domain.geojson", "domain block 2", crs)
    outs = h.add_vector(
        h.geojson("outs", [h.line(k["coordinates"], kind="normal", value=0.01) for k in jobs["boundaries"]]), "outlets", crs
    )
    lines = h.add_vector(
        h.geojson("dams", [h.line(k["coordinates"], name=k["name"]) for k in jobs["outputs"]["lines"] if k["name"] in DAMS]),
        "dam lines", crs,
    )  # fmt: skip
    dock = yield from h.open_dock()
    t, hy = dock.terrain, dock.hydrology

    h.log("=== 1 the combo before any project")
    combo = hy.routing
    schemes = [combo.itemData(i) for i in range(combo.count())]
    h.check("the choices are the engine's two schemes, HMS-faithful first", schemes == dock.schema.enum("hydrology.reach_routing") == [HMS_SCHEME, CONSERVING_SCHEME], schemes)
    h.check("HMS-faithful is the default", combo.currentData() == HMS_SCHEME == dock.schema.default("hydrology.reach_routing"), combo.currentData())
    h.check("each choice has words of its own", len({combo.itemText(i) for i in range(combo.count())}) == 2 and all(combo.itemText(i) != combo.itemData(i) for i in range(combo.count())), [combo.itemText(i) for i in range(combo.count())])
    h.check("the tooltip is the schema's", "Todini" in combo.toolTip() and "HEC-HMS" in combo.toolTip(), combo.toolTip()[:80])
    h.widget_shot("hydrology_routing", hy)

    t.dem.setLayer(dem)
    t.dx.setValue(DX)
    t.domain.setLayer(block)
    t.manning.box.setValue(0.1)
    dock.boundaries.layer.setLayer(outs)
    dock.points.layer.setLayer(lines)
    dock.points.name.setField("name")
    dock.panel.pixels.setChecked(False)
    hy.folder.setFilePath(str(h.BLOCK / "HEC_HMS_Block_02"))
    hy.files["basin"].setCurrentText("Basin_1.basin")
    hy.files["met"].setCurrentText("FM_100yr.met")
    hy.files["control"].setCurrentText("Control_1.control")
    h.check("18 HMS subbasins, all lumped", hy.table.rowCount() == 18 and all(hy.table.cellWidget(r, 1).currentText() == "lumped" for r in range(18)))
    h.check("the combo is still there and still HMS-faithful under an HMS project", combo.isEnabled() and combo.currentData() == HMS_SCHEME)

    h.log("=== 2 the default run: the job says 'hms', the engine resolves 'hms'")
    first = h.RUNS / "block2_hms"
    dock.panel.folder.setFilePath(str(first))
    yield from h.run(dock, limit=2000)
    h.check("the HMS-faithful run finished", done_event(h, first).get("code") == 0, dock.panel.message.text()[:300])
    job = json.loads((first / "job.json").read_text(encoding="utf-8"))
    h.check("job.json says hms", job["hydrology"].get("reach_routing") == HMS_SCHEME, job["hydrology"].get("reach_routing"))
    h.check("the resolved job says hms", resolved_scheme(first) == HMS_SCHEME, resolved_scheme(first))
    h.check("mass closes", abs(done_event(h, first)["balance"].get("relative_error", 1.0)) < 1e-6)

    h.log("=== 3 the conserving run")
    combo.setCurrentIndex(combo.findData(CONSERVING_SCHEME))
    values = dock._collect()
    h.check("the collected values carry the choice", values.get("reach_routing") == CONSERVING_SCHEME, values.get("reach_routing"))
    second = h.RUNS / "block2_conserving"
    dock.panel.folder.setFilePath(str(second))
    yield from h.run(dock, limit=2000)
    h.check("the conserving run finished", done_event(h, second).get("code") == 0, dock.panel.message.text()[:300])
    job2 = json.loads((second / "job.json").read_text(encoding="utf-8"))
    h.check("job.json says conserving", job2["hydrology"].get("reach_routing") == CONSERVING_SCHEME, job2["hydrology"].get("reach_routing"))
    h.check("the resolved job says conserving", resolved_scheme(second) == CONSERVING_SCHEME, resolved_scheme(second))
    h.check("mass closes", abs(done_event(h, second)["balance"].get("relative_error", 1.0)) < 1e-6)
    others = [{k: v for k, v in j["hydrology"].items() if k != "reach_routing"} for j in (job, job2)]
    h.check("nothing else of the job changed", others[0] == others[1] and {k for k in job if k != "hydrology"} == {k for k in job2 if k != "hydrology"}, [k for k in others[0] if others[0][k] != others[1].get(k)])

    h.log("=== 4 the reach series: a headwater reach takes the same inflow, every outflow differs, none gains")
    record = {"dx": DX, "reaches": {}, "dams": {}}
    headwaters = []
    for name in REACHES:
        t1, in1, out1 = series(first, name)
        t2, in2, out2 = series(second, name)
        same_in = t1 == t2 and max(abs(a - b) for a, b in zip(in1, in2, strict=True)) == 0.0
        differ = max(abs(a - b) for a, b in zip(out1, out2, strict=True)) > 1e-6
        ratio_hms = trapezoid(t1, out1) / trapezoid(t1, in1)
        ratio_con = trapezoid(t2, out2) / trapezoid(t2, in2)
        record["reaches"][name] = {"hms": peak(t1, out1), "conserving": peak(t2, out2), "out_in_hms": round(ratio_hms, 5), "out_in_conserving": round(ratio_con, 5), "window_h": round(t1[-1] / 3600.0, 1)}
        if same_in:
            headwaters.append(name)
        h.check(f"{name}: a different outflow, no volume gained, never negative", differ and ratio_con <= 1.0 + 1e-9 and min(out2) >= -1e-9 * max(out2), (same_in, differ, ratio_hms, ratio_con))
    h.check("the headwater reaches take the same inflow in both runs; the others take what the scheme above gave", 0 < len(headwaters) < len(REACHES), headwaters)
    for dam in DAMS:
        t1, in1, _ = series(first, dam)
        t2, in2, _ = series(second, dam)
        record["dams"][dam] = {"hms": peak(t1, in1), "conserving": peak(t2, in2)}
    record["dam_lines_2d"] = {"hms": h.peaks(first), "conserving": h.peaks(second)}
    h.log(f"reaches: {record['reaches']}")
    h.log(f"dams: {record['dams']}")
    h.log(f"2D lines: {record['dam_lines_2d']}")
    h.check("every dam peak within 10 % of the HMS-faithful run's", all(abs(record["dams"][d]["conserving"]["peak_m3s"] / record["dams"][d]["hms"]["peak_m3s"] - 1.0) < 0.1 for d in DAMS), record["dams"])
    (h.P / "block2_routing_peaks.json").write_text(json.dumps(record, indent=1), encoding="utf-8")

    h.log("=== 5 back to the default")
    combo.setCurrentIndex(combo.findData(HMS_SCHEME))
    from wadi2d_qgis.job_builder import build_job

    job3 = build_job(dock._collect(), h.RUNS / "job3")
    h.check("the HMS choice writes hms again", job3["hydrology"].get("reach_routing") == HMS_SCHEME, job3["hydrology"].get("reach_routing"))
    h.widget_shot("hydrology_final", hy)
