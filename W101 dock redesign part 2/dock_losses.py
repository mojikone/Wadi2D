"""W101 item 2 through the real dock: Manning in its four forms (Terrain) and the CN override (Hydrology).

Each form shows only its fields, writes the job the engine's schema takes, and one value or a grid write the job the
dock always wrote; what stops a run is said in words; a model from before with a Manning raster opens as a grid; the
forms are saved and brought back; a real run on Bidah with Manning by land-use class and the CN by range.
"""

import json
from pathlib import Path


def scenario(h):
    import importlib.util

    spec = importlib.util.spec_from_file_location("w101_help", Path(h.SCENARIO).parent / "w101_help.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    ground = h.Bidah()
    dock = yield from h.open_dock()
    from wadi2d_qgis.section_status import MISSING

    t, hy = dock.terrain, dock.hydrology
    out = h.RUNS / "built"
    h.set_rain_job(dock, ground, "losses", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=False)
    landuse = h.add_raster(w.constant_raster(h.DATA / "landuse_one.tif", ground.dem, 1.0), "w101 land use")
    t.setCollapsed(False)
    hy.setCollapsed(False)

    h.log("=== 1 Manning in four forms")
    forms = [t.manning_form.itemData(i) for i in range(t.manning_form.count())]
    h.check("four forms", forms == ["uniform", "split", "grid", "land_use"], forms)
    plain = w.built(dock, out)
    h.check("one value: the job of before", "roughness" not in plain["terrain"] and plain["terrain"]["manning"] == t.manning.value())
    h.check("one value shows its number alone", t.manning.box.isVisibleTo(t) and not t.manning.raster.isVisibleTo(t) and not t.manning_aligned.isVisibleTo(t) and not t.rough_classes.isVisibleTo(t))
    t.manning.raster.setLayer(landuse)
    h.check("a raster chosen makes it a grid, as a model from before opens", t.manning_form.currentData() == "grid" and w.built(dock, out)["terrain"]["manning_raster"] == str(Path(landuse.source()).resolve()))
    w.pick(t.manning_form, "uniform")
    h.check("back to one value drops the raster", t.manning.raster.currentLayer() is None and "manning_raster" not in w.built(dock, out)["terrain"])
    w.pick(t.manning_form, "split")
    h.check("squares and aligned apart shows the aligned cells' n", t.manning_aligned.isVisibleTo(t))
    h.check("and is refused without the aligned cells, in words", any("aligned cells" in p for p in w.problems_of(dock, out)))
    w.pick(t.manning_form, "land_use")
    t.rough_landuse.setLayer(landuse)
    h.check("land-use classes with no table: Missing in words", dock.status_links.refresh()["terrain"].state == MISSING and "table" in dock.status_links.refresh()["terrain"].words, dock.status_links.refresh()["terrain"])
    t.rough_classes.set_rows([(1.0, 0.05, "the whole of it")])
    job = w.built(dock, out)
    h.check("land-use classes: the job's roughness", job["terrain"]["roughness"] == {"form": "land_use", "land_use": str(Path(landuse.source()).resolve()), "classes": [{"code": 1, "n": 0.05, "name": "the whole of it"}]} and "manning_raster" not in job["terrain"], job["terrain"].get("roughness"))
    w.validated(job)
    w.big_shot(h, dock, "terrain_land_use", open_only="terrain")
    dock.types.choose("lumped")
    h.check("a Lumped model asks for no Manning in any form", not t.manning_form.isVisibleTo(t) and not t.rough_classes.isVisibleTo(t) and not t.rough_landuse.isVisibleTo(t))
    dock.types.choose(None)

    h.log("=== 2 the CN override")
    hy.cn.box.setValue(80.0)
    bys = [hy.cn_by.itemData(i) for i in range(hy.cn_by.count())]
    h.check("none and three forms", bys == ["none", "land_use", "range", "subbasin"], bys)
    h.check("none: no table, no job part", not hy.cn_table.isVisibleTo(hy) and "cn_override" not in w.built(dock, out)["hydrology"])
    w.pick(hy.cn_by, "subbasin")
    h.check("by subbasin: two columns", hy.cn_table.table.columnCount() == 2)
    w.pick(hy.cn_by, "range")
    h.check("by range: three columns, the raster hidden", hy.cn_table.table.columnCount() == 3 and not hy.cn_landuse.isVisibleTo(hy))
    hy.cn_table.set_rows([(1.0, 60.0, 70.0), (50.0, 100.0, 90.0)])
    h.check("overlapping ranges: Missing in words", dock.status_links.refresh()["hydrology"].state == MISSING and "overlap" in dock.status_links.refresh()["hydrology"].words)
    hy.cn_table.set_rows([(1.0, 100.0, 90.0)])
    job = w.built(dock, out)
    h.check("by range: the job's override", job["hydrology"]["cn_override"] == {"by": "range", "ranges": [{"low": 1.0, "high": 100.0, "curve_number": 90.0}]}, job["hydrology"].get("cn_override"))
    w.validated(job)
    h.check("the card says so", "CN override" in dock.status_links.refresh()["hydrology"].words, dock.status_links.refresh()["hydrology"].words)
    w.big_shot(h, dock, "hydrology_cn_override", open_only="hydrology")

    h.log("=== 3 saved and brought back")
    before = w.built(dock, out)
    doc = dock.model.collect()
    dock.model.reset()
    dock.model.apply(doc)
    h.check("the same job after the round trip", w.built(dock, out) == before)
    h.check("the forms came back", t.manning_form.currentData() == "land_use" and hy.cn_by.currentData() == "range" and hy.cn_table.rows() == [(1.0, 100.0, 90.0)])

    h.log("=== 4 a real run with both")
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    dock.panel.folder.setFilePath(str(h.RUNS / "losses_run"))
    yield from h.run(dock)
    run = dock.results_dir
    done = h.events(run, "done")
    h.check("finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text())
    resolved = json.loads((run / "config.resolved.json").read_text(encoding="utf-8"))
    h.check("the engine read the land-use Manning", resolved["terrain"]["roughness"]["form"] == "land_use")
    h.check("and the CN by range", resolved["hydrology"]["cn_override"]["ranges"][0]["curve_number"] == 90.0)
