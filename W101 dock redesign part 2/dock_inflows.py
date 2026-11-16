"""W101 item 3 through the real dock: a flow line's hydrograph typed as a table at a time step, with its chart and
energy slope, beside the file route; and initial-level points with the start water in Structures.

The box shows the flow line chosen in the table; the job carries HEC-RAS's table (``flow.step_s`` and ``flows``), the
engine's schema takes it; a short table is refused in words; the rows are saved and brought back; a real Bidah run
takes the typed inflow.
"""

import json
from pathlib import Path


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w101_help", Path(h.SCENARIO).parent / "w101_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    ground = h.Bidah()
    jobs = json.loads((h.VALIDATION / "jobs" / "c10_A74_h100.json").read_text(encoding="utf-8"))
    dam = next(k["coordinates"] for k in jobs["outputs"]["lines"] if k["name"] == "Bidah 03")
    lines = [h.line(k["coordinates"], kind="normal", value=0.01) for k in ground.outlets_data]
    lines.append(h.line(dam, kind="flow", name="Inflow at the dam"))
    edges = h.add_vector(h.geojson("w101_edges", lines), "w101 edges", ground.crs)
    box = ground.domain.extent().center()
    point = {"type": "Feature", "properties": {"level": 999.0, "name": "a point"}, "geometry": {"type": "Point", "coordinates": [box.x(), box.y()]}}
    points = h.add_vector(h.geojson("w101_points", [point]), "w101 level points", ground.crs)
    dock = yield from h.open_dock()

    b, s = dock.boundaries, dock.structures
    out = h.RUNS / "built"
    h.set_rain_job(dock, ground, "inflows", dx=30.0, rain=10.0, hours=0.5, sim_hours=0.75, pixels=False)
    b.layer.setLayer(edges)
    b.setCollapsed(False)

    h.log("=== 1 the hydrograph of the flow line, typed")
    flow_row = next(n for n, row in enumerate(b.rows) if row.kind == "flow")
    b.table.setCurrentCell(flow_row, 0)
    hb = b.hydrograph
    h.check("the box shows the flow line chosen", hb.isVisibleTo(b) and hb.row is b.rows[flow_row])
    b.table.setCurrentCell(0, 0)
    h.check("and hides for a normal-depth line", not hb.isVisibleTo(b))
    b.table.setCurrentCell(flow_row, 0)
    h.check("a file route first: missing in words", dock.status_links.refresh()["boundaries"].state == "missing")
    w.pick(hb.source, True)
    hb.step.setValue(15.0)
    hb.slope.setValue(0.01)
    hb.flows.set_rows([(0.0,), (50.0,), (20.0,), (0.0,)])
    row = b.rows[flow_row]
    h.check("the row holds the table", row.typed and row.step_min == 15.0 and row.flows == [0.0, 50.0, 20.0, 0.0] and row.slope == 0.01, row)
    h.check("its chart: four flows, a quarter-hour apart", hb.chart.xs == [0.0, 0.25, 0.5, 0.75] and hb.chart.ys == [0.0, 50.0, 20.0, 0.0], (hb.chart.xs, hb.chart.ys))
    h.check("the card ready, in words", dock.status_links.refresh()["boundaries"].state == "ready", dock.status_links.refresh()["boundaries"])
    job = w.built(dock, out)
    flow = next(line["flow"] for line in job["boundaries"] if line["kind"] == "flow")
    h.check("the job carries HEC-RAS's table", flow == {"step_s": 900.0, "flows": [0.0, 50.0, 20.0, 0.0], "slope": 0.01}, flow)
    h.check("the engine's schema takes it", w.validated(job).boundaries[-1].flow.flows == [0.0, 50.0, 20.0, 0.0])
    hb.flows.set_rows([(5.0,)])
    h.check("one flow is refused in words", any("two flows at least" in p for p in w.problems_of(dock, out)))
    hb.flows.set_rows([(0.0,), (50.0,), (20.0,), (0.0,)])
    w.big_shot(h, dock, "boundaries_typed", open_only="boundaries")

    h.log("=== 2 initial-level points")
    s.setCollapsed(False)
    s.start_water.points.setLayer(points)
    s.start_water.point_level.setField("level")
    s.start_water.point_name.setField("name")
    job = w.built(dock, out)
    h.check("the job's initial points", job.get("initial_points") == [{"name": "a point", "x": box.x(), "y": box.y(), "level": 999.0}], job.get("initial_points"))
    w.validated(job)
    s.start_water.point_level.setField("")
    h.check("no level field: refused in words", any("need a level" in p for p in w.problems_of(dock, out)))
    s.start_water.points.setLayer(None)

    h.log("=== 3 saved and brought back")
    before = w.built(dock, out)
    doc = dock.model.collect()
    dock.model.reset()
    dock.model.apply(doc)
    h.check("the same job after the round trip", w.built(dock, out) == before)
    h.check("the typed rows came back", b.rows[flow_row].typed and b.rows[flow_row].flows == [0.0, 50.0, 20.0, 0.0])

    h.log("=== 4 a real run with the typed inflow")
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    dock.panel.folder.setFilePath(str(h.RUNS / "inflow_run"))
    yield from h.run(dock)
    run = dock.results_dir
    done = h.events(run, "done")
    h.check("finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text())
    resolved = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
    flow = next(line["flow"] for line in resolved["boundaries"] if line["kind"] == "flow")
    h.check("the engine read the table", flow["step_s"] == 900.0 and flow["flows"] == [0.0, 50.0, 20.0, 0.0])
    balance = [e for e in h.events(run, "done")][-1]
    h.log(f"done event: {json.dumps(balance)[:400]}")
