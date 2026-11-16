"""W103: the four Block 2 jobs of W79 imported into the dock again, now that Hydrology holds each subbasin's own storm
area, entry and outlet and the point inflows of lumped elements; saved as scenarios in W103 and proved field by field
as W101 proved them (W101 ``dock_import_block2.py``, whose steps this repeats). Then the new controls through the
dock: the columns and the table, the status line, a scenario saved and opened again to the same job, an outlet that is
no point refused in words, Click on the map. Last, the dock's own way for the two Hybrids: the lumped part of the area
reduction a curve (W98) instead of the hand-typed storm areas, and for Hybrid Lumped the lumped water kept on the
network (W88) instead of the six hand-placed inflows; saved as two more scenarios with their jobs, for the engine to
compare (``scripts/compare_dock_way.py``). Read-only on his folders and on W79 and W102; no 2D solver runs.
"""

import json
from pathlib import Path

W79 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W79 Block 2 four ways")
W103 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W103 Block 2 scenarios complete")
JOBS = (
    ("2D", "rerun2_run1_full_2d_aligned", "2d"),
    ("Lumped", "rerun2_run2_hms_lumped", "lumped"),
    ("Hybrid Lumped", "rerun2_run3_hybrid_aligned", "hybrid_lumped"),
    ("Hybrid 2D", "rerun2_run4_hybrid_2d_routing_aligned", "hybrid_2d"),
)
DOCK_WAY = (
    ("Hybrid Lumped, dock way", "Hybrid Lumped", "hybrid_lumped_dock_way"),
    ("Hybrid 2D, dock way", "Hybrid 2D", "hybrid_2d_dock_way"),
)
STILL_NOT_HELD = {"Hydrology": ["hydrology.curve_number"], "Simulation": ["outputs.live_every_s", "run.checkpoint_every_s"]}
"""What W102 found besides the two gaps, which W103 leaves (not in its brief)."""
LUMPED_ONLY = "run.lumped_only"
"""And on Lumped: the dock's Lumped type writes it, the job does not (W79 ran it lumped by a script; W102)."""


def expected(name: str) -> dict:
    if name != "Lumped":
        return STILL_NOT_HELD
    return {**STILL_NOT_HELD, "Simulation": [*STILL_NOT_HELD["Simulation"], LUMPED_ONLY]}


def resolved(job: dict) -> dict:
    """A job as the engine reads it: every default written out, the domain as its polygon."""
    from wadi2d.config.schema import RunConfig
    from wadi2d_qgis.job_import import in_phase_order

    out = in_phase_order(RunConfig.model_validate(job).model_dump(mode="json"))
    domain = (out.get("grid") or {}).get("domain")
    if domain and Path(domain).is_file():
        out["grid"]["domain"] = [f["geometry"]["coordinates"] for f in json.loads(Path(domain).read_text(encoding="utf-8"))["features"]]
    return out


def write_job(h, dock, out: Path):
    """The job the dock writes now, as Run writes it (the HMS import included). Use: ``job = yield from ...``."""
    made = {}
    values = dock._collect()
    values["output"] = str(out)
    dock._prepare(values, out, lambda path: made.update(job=json.loads(Path(path).read_text(encoding="utf-8"))),
                  lambda text: made.update(error=text), lambda text, _tone="info": None)  # fmt: skip
    yield lambda: made
    h.check(f"the dock writes its job into {out.name}", "job" in made, made.get("error", ""))
    return made.get("job")


def scenario(h):
    dock = yield from h.open_dock()
    from qgis.core import QgsPointXY, QgsProject
    from wadi2d_qgis.entry_rows import NO_OUTLET
    from wadi2d_qgis.job_import import not_held
    from wadi2d_qgis.sections.hydrology import AREA, ENTRY, OUTLET

    W103.mkdir(exist_ok=True)
    report = {}
    saved = {}
    hyd = dock.hydrology
    for name, stem, kind in JOBS:
        h.log(f"=== {name}: {stem}")
        source = W79 / "jobs" / f"{stem}.json"
        original = json.loads(source.read_text(encoding="utf-8"))
        dock.panel.folder.setFilePath(str(W103))
        words = dock.model.import_job(str(source))
        h.check(f"{name}: imported", bool(dock.terrain.dem_layer()) and dock.panel.folder.filePath() == str(W103), dock.model_bar.message.text()[:300])
        dock.types.choose(kind)
        subs = original["hydrology"].get("subbasins") or []
        own = {s["name"]: s["storm_area_km2"] for s in subs if s.get("storm_area_km2") is not None}
        inflows = [i for i in original["hydrology"].get("inflows") or [] if i.get("element")]
        if original["hydrology"].get("hms_basin"):
            edits = hyd.subbasin_edits()
            held = {n: e["storm_area_km2"] for n, e in edits.items() if "storm_area_km2" in e}
            h.check(f"{name}: each subbasin's own storm area held ({len(own)})", held == own, (len(held), len(own)))
            cleared = sorted(n for n, e in edits.items() if e.get("outlet") == NO_OUTLET)
            gone = sorted(s["name"] for s in subs if not s.get("outlet"))
            h.check(f"{name}: the outlets the job took away held ({len(gone)})", cleared == gone, (len(cleared), len(gone)))
            h.check(f"{name}: the columns shown on the HMS project", not any(hyd.table.isColumnHidden(c) for c in (AREA, ENTRY, OUTLET)))
        rows = hyd.inflows.rows()
        h.check(
            f"{name}: its {len(inflows)} point inflows held by element",
            [(r[0], r[1], round(r[2], 6), round(r[3], 6)) for r in rows] == [(i["name"], i["element"], round(i["x"], 6), round(i["y"], 6)) for i in inflows],
            rows,
        )  # fmt: skip
        dock.model.compare_job(original)  # with the type the scenario is
        yield lambda: dock.model.comparison is not None
        dock_words, dock_found = dock.model.comparison
        standing = {section.key: section.standing(kind) for section in dock.sections}
        h.log(f"{name}: hydrology reads: {standing['hydrology'].words}")
        path = dock.model.save_scenario(name)
        h.check(f"{name}: saved as a scenario", path is not None and path.is_file(), str(path))
        saved[name] = path
        job = yield from write_job(h, dock, W103 / "rebuilt" / stem)
        if job is None:
            continue
        engine_found = not_held(resolved(original), resolved(job))
        h.log(f"{name}: not held by the engine's reading: {json.dumps(engine_found)}")
        known = expected(name)
        h.check(f"{name}: the job is the original but for {known}", all(set(paths) <= set(known.get(k, [])) for k, paths in engine_found.items()), engine_found)
        h.check(f"{name}: the dock's own comparison agrees", set(dock_found or {}) <= set(engine_found) | {"Other"} or not dock_found, (dock_found, engine_found))
        report[name] = {
            "job": str(source), "scenario": str(path), "rebuilt_job": str(W103 / "rebuilt" / stem / "job.json"),
            "model_type": kind, "import_words": words, "dock_comparison": dock_words,
            "not_held_by_the_engines_reading": engine_found,
            "inline_layers": {lyr.name(): lyr.source() for lyr in QgsProject.instance().mapLayers().values() if "imported_inputs" in lyr.source()},
            "sections": {key: [status.state, status.words] for key, status in standing.items()},
        }  # fmt: skip

    h.log("=== the new controls, on Hybrid Lumped")
    dock.model.open_scenario(str(saved["Hybrid Lumped"]))
    dock.types.choose("hybrid_lumped")
    first = yield from write_job(h, dock, W103 / "checks" / "opened_again")
    rebuilt = json.loads((W103 / "rebuilt" / "rerun2_run3_hybrid_aligned" / "job.json").read_text(encoding="utf-8"))
    same = lambda a, b: json.dumps(resolved(a)["hydrology"], sort_keys=True) == json.dumps(resolved(b)["hydrology"], sort_keys=True)  # noqa: E731
    h.check("a scenario opened again writes the same hydrology", first is not None and same(first, rebuilt))
    status = hyd.standing("hybrid_lumped")
    h.check("the status line counts what is set", status.state == "ready" and "26 at a storm area of their own" in status.words and "6 point inflows" in status.words, status.words)
    row = next(n for n in range(hyd.table.rowCount()) if hyd.table.item(n, 0).text() == "S13")
    cell = hyd.table.cellWidget(row, OUTLET)
    held = cell.text()
    cell.setText("below the dam")
    cell.editingFinished.emit()
    status = hyd.standing("hybrid_lumped")
    h.check("an outlet that is no point is Missing, in words", status.state == "missing" and 'the outlet "below the dam" is not a point' in status.words, status.words)
    heard = []
    refused = dock._checked_values(say=lambda text, _tone="info": heard.append(text))
    h.check("and Run refuses it in the same words", refused is None and any('"below the dam" is not a point' in t for t in heard), heard)
    cell.setText(held)
    cell.editingFinished.emit()
    h.check("written back, it is Ready again", hyd.standing("hybrid_lumped").state == "ready", hyd.standing("hybrid_lumped").words)
    area = hyd.table.cellWidget(row, AREA)
    h.check("S13 reads Bidah 03's 20.97 km2", abs(area.value() - 20.97) < 1e-9, area.value())
    h.widget_shot("hydrology_subbasins_and_inflows", hyd)
    count = len(hyd.inflows.rows())
    hyd.inflows.place_button.setChecked(True)
    h.check("Click on the map takes the canvas", dock.iface.mapCanvas().mapTool() is dock.inflow_points.tool)
    dock.inflow_points._clicked(QgsPointXY(438700.0, 2727100.0))
    rows = hyd.inflows.rows()
    h.check("a click adds a row at its point in the DEM's coordinates", len(rows) == count + 1 and rows[-1][2:4] == (438700.0, 2727100.0) and not hyd.inflows.place_button.isChecked(), rows[-1])
    h.check("and gives the tool back", dock.iface.mapCanvas().mapTool() is not dock.inflow_points.tool)
    hyd.inflows.table.selectRow(count)
    hyd.inflows.drop_button.click()
    h.check("Remove row takes it out", hyd.inflows.rows() == rows[:-1], len(hyd.inflows.rows()))
    dock.types.choose("2d")
    values = dock._collect()
    h.check("a 2D model carries no point inflow and no edit", "inflows" not in values and "hms" not in values)
    dock.types.choose("hybrid_lumped")

    h.log("=== the dock's own way")
    for title, base, folder in DOCK_WAY:
        dock.model.open_scenario(str(saved[base]))
        kind = "hybrid_lumped" if base == "Hybrid Lumped" else "hybrid_2d"
        dock.types.choose(kind)
        lumped = dock.reduction.lumped
        lumped.form.setCurrentIndex(lumped.form.findData("curve"))
        lumped.curve.setCurrentIndex(lumped.curve.findData("Area reduction"))
        hyd.set_edits({})  # the HMS import's subbasins, no storm area typed by hand
        hyd.inflows.set_rows([])
        if kind == "hybrid_lumped":
            hyd.lumped_entry.setCurrentIndex(hyd.lumped_entry.findData("network"))
        h.check(f"{title}: the lumped part a curve, the 2D part at 100 km2", dock.reduction.reduction()["lumped"]["form"] == "curve" and dock.reduction.reduction()["grid"]["area_km2"] == 100.0, dock.reduction.reduction())
        path = dock.model.save_scenario(title)
        h.check(f"{title}: saved as a scenario", path is not None and path.is_file(), str(path))
        job = yield from write_job(h, dock, W103 / "rebuilt" / folder)
        if job is None:
            continue
        reduction = (job.get("storm") or {}).get("area_reduction") or {}
        h.check(f"{title}: the job reads the lumped curve at the entries", reduction.get("lumped", {}).get("form") == "curve", reduction)
        h.check(f"{title}: no own storm area and no hand-placed inflow", not any(s.get("storm_area_km2") for s in job["hydrology"]["subbasins"]) and not job["hydrology"].get("inflows"))
        if kind == "hybrid_lumped":
            h.check(f"{title}: the lumped water kept on the network", job["hydrology"].get("lumped_entry") == "network" and job["grid"].get("exclude_lumped") is True)
        report[title] = {"scenario": str(path), "rebuilt_job": str(W103 / "rebuilt" / folder / "job.json"), "model_type": kind}
    (W103 / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    h.check("the report written", (W103 / "report.json").is_file())
