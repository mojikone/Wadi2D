"""W99 step 2 through the real dock: the model type is chosen first, shows only its sections, and reaches the job.

The start page as a user meets it (four cards and a run to open), each type's sections and Hydrology rows, the three
ticks the type sets, the job each type writes, a real run of the 2D type, the type saved with the model and read back,
and a model with no word on its type, which gets the one it runs as.
"""

import importlib.util
import json
import shutil
from pathlib import Path

from qgis.core import QgsProject


def helper(h, name="model_fill"):
    spec = importlib.util.spec_from_file_location(name, Path(h.SCENARIO).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def big_shot(h, dock, name, size=(440, 900)):
    """The dock's frame drawn at the width of a real dock: in the test window it is docked far narrower."""
    from qgis.PyQt.QtWidgets import QApplication

    frame = dock.widget()
    held = frame.size()
    frame.resize(*size)
    QApplication.processEvents()
    frame.grab().save(str(h.P / f"widget_{name}.png"))
    frame.resize(held)
    QApplication.processEvents()


def shown(dock):
    """The keys of the sections a user sees now."""
    return [section.key for section in dock.sections if section.isVisible()]


def scenario(h):
    mf = helper(h)
    ground = h.Bidah()
    dock = yield from h.open_dock(all_sections=False)
    from wadi2d_qgis.job_builder import problems
    from wadi2d_qgis.model_types import ALL_SECTIONS, TYPES

    start, header, hy, types = dock.start_page, dock.header, dock.hydrology, dock.types
    yield lambda: True

    h.log("=== 1 the dock opens on the start page")
    h.check("the start page is the one showing", dock.pages.currentIndex() == 0 and start.isVisible())
    h.check("four cards, in the engine's own names", list(start.cards) == ["2d", "lumped", "hybrid_lumped", "hybrid_2d"], list(start.cards))
    h.check("the section keys are the dock's", tuple(s.key for s in dock.sections) == ALL_SECTIONS, [s.key for s in dock.sections])
    h.check("the engine knows the four types", sorted(dock.schema.enum("run.model_type")) == sorted(TYPES), dock.schema.enum("run.model_type"))
    for key, card in start.cards.items():
        h.check(f"card {key}: title, badge and meaning in words", bool(card.title.text() and card.badge.text() and len(card.meaning.text()) > 20), card.meaning.text())
    h.check("no section shows on the start page", shown(dock) == [], shown(dock))
    h.check("the engine line stays in sight", dock.engine_label.isVisible() and dock.engine_button.isVisible())
    big_shot(h, dock, "start_page")
    dock.model.keep()
    h.check("looking at the start page changes no project", not QgsProject.instance().readEntry("Wadi2D", "model", "")[1])

    h.log("=== 2 2D: every section, no lumped part")
    start.cards["2d"].click()
    yield lambda: True
    h.check("the model page shows", dock.pages.currentIndex() == 1 and header.isVisible())
    h.check("2D: the header names the type in words and as a badge", "2D" in header.title.text() and header.badge.text() == "2D", header.title.text())
    h.check("2D: all sections show", shown(dock) == list(ALL_SECTIONS), shown(dock))
    h.check("2D: Hydrology shows no lumped row", not hy.lumped_box.isVisible() and hy.cn.isVisible() and hy.loss.isVisible())
    h.check("2D: no Show all switch, nothing is hidden", not header.show_all.isVisible())
    h.set_rain_job(dock, ground, "two_d", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=False)
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    job = mf.built(dock, h.RUNS / "job")
    h.check("2D: the job names its type", job["run"].get("model_type") == "2d", job["run"])
    h.check("2D: nothing else moved in the job", set(job["run"]) == {"duration_s", "backend", "model_type"} and "exclude_lumped" not in job["grid"], job["run"])
    dock.terrain.setCollapsed(True)
    big_shot(h, dock, "model_page_2d")

    h.log("=== 3 a real run of the 2D type: the engine takes the job")
    yield from h.run(dock)
    run = h.RUNS / "two_d"
    done = h.events(run, "done")
    h.check("the 2D run finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text()[:200])
    h.check("the run's job names the type", json.loads((run / "job.json").read_text(encoding="utf-8"))["run"].get("model_type") == "2d")
    saved = json.loads((run / "model.wadi2d.json").read_text(encoding="utf-8"))
    h.check("the run's model names the type", saved.get("model_type") == "2d" and saved.get("page") == "model", (saved.get("model_type"), saved.get("page")))

    h.log("=== 4 the way back, and Lumped: no mesh, no boundaries, no study")
    header.back_button.click()
    yield lambda: True
    h.check("back on the start page", dock.pages.currentIndex() == 0)
    h.check("the chosen card is marked", start.cards["2d"].property("current") == "true" and start.cards["lumped"].property("current") == "false")
    h.check("nothing in the sections was lost on the way back", dock.terrain.dx.value() == 30.0 and dock.panel.duration.value() == 0.75)
    start.cards["lumped"].click()
    yield lambda: True
    hidden = [key for key in ALL_SECTIONS if key not in shown(dock)]
    h.check("Lumped: mesh, boundaries and the depth-area study are not shown", hidden == ["mesh", "boundaries", "study"], hidden)
    h.check("Lumped: the header says so", header.badge.text() == "LUMP" and "HMS way" in header.meaning.text(), header.meaning.text())
    h.check("Lumped: the lumped rows show", hy.lumped_box.isVisible() and hy.folder.isVisible() and hy.basin.isVisible())
    found = problems(dock._collect())
    h.check("Lumped with no network: said in words before a run", any("Lumped model needs its lumped catchments" in text for text in found), found)
    hms = h.P / "hms"
    hms.mkdir(exist_ok=True)
    for name in ("Basin_3.basin", "FM_200yr.met", "Control_1.control"):
        shutil.copy2(h.BLOCK / "HEC_HMS_Block_02" / name, hms / name)
    hy.folder.setFilePath(str(hms))
    yield lambda: hy.files["basin"].count() > 0
    hy.files["basin"].setCurrentText("Basin_3.basin")
    hy.files["met"].setCurrentText("FM_200yr.met")
    hy.files["control"].setCurrentText("Control_1.control")
    dock.storm.kind.setCurrentIndex(dock.storm.kind.findData("hms"))
    yield lambda: hy.table.rowCount() > 0
    h.check("Lumped: the HMS-way tick is the type's, not shown", not hy.lumped_only.isVisible() and hy.lumped_only.isChecked())
    h.check("Lumped: no entry into a 2D model to choose", not hy.lumped_entry.isVisible() and not hy.exclude.isVisible())
    h.check("Lumped: each element at its own area stays a choice", hy.arf_by_element.isVisible() and hy.arf_by_element.isEnabled())
    hy.arf_by_element.setChecked(True)
    h.check("Lumped with a network: nothing stops it", problems(dock._collect()) == [], problems(dock._collect()))
    job = mf.built(dock, h.RUNS / "job")
    h.check("Lumped: the job is the lumped network alone", job["run"].get("lumped_only") is True and job["run"].get("model_type") == "lumped", job["run"])
    h.check("Lumped: the element areas reach the job", job["hydrology"].get("arf_by_element") is True, job["hydrology"])
    header.show_all.setChecked(True)
    yield lambda: True
    h.check("Lumped, Show all sections: the old full list", shown(dock) == list(ALL_SECTIONS), shown(dock))
    h.check("Lumped, Show all sections: the type still owns its tick", not hy.lumped_only.isVisible())
    header.show_all.setChecked(False)
    hy.setCollapsed(False)
    big_shot(h, dock, "model_page_lumped")

    h.log("=== 5 Hybrid Lumped: catchments left out of the mesh, the entry a choice")
    header.back_button.click()
    start.cards["hybrid_lumped"].click()
    yield lambda: True
    h.check("Hybrid Lumped: all sections show", shown(dock) == list(ALL_SECTIONS), shown(dock))
    h.check("Hybrid Lumped: left-out and HMS-way ticks are the type's", not hy.exclude.isVisible() and not hy.lumped_only.isVisible() and hy.exclude.isChecked() and not hy.lumped_only.isChecked())
    h.check("Hybrid Lumped: where the lumped water enters is a choice", hy.lumped_entry.isVisible() and hy.lumped_entry.isEnabled())
    h.check("Hybrid Lumped: no per-element area reduction", not hy.arf_by_element.isVisible())
    hy.lumped_entry.setCurrentIndex(hy.lumped_entry.findData("network"))
    job = mf.built(dock, h.RUNS / "job")
    h.check("Hybrid Lumped: the job leaves the catchments out", job["grid"].get("exclude_lumped") is True and job["run"].get("model_type") == "hybrid_lumped" and "lumped_only" not in job["run"], (job["grid"].keys(), job["run"]))
    h.check("Hybrid Lumped: the chosen entry reaches the job", job["hydrology"].get("lumped_entry") == "network" and "arf_by_element" not in job["hydrology"], job["hydrology"])

    h.log("=== 6 Hybrid 2D: catchments kept, entering at their outlets")
    header.back_button.click()
    start.cards["hybrid_2d"].click()
    yield lambda: True
    h.check("Hybrid 2D: the three ticks are the type's", not hy.exclude.isVisible() and not hy.lumped_only.isVisible() and not hy.lumped_entry.isVisible())
    h.check("Hybrid 2D: the subbasin table stays a choice", hy.table.isVisible() and hy.table.rowCount() > 0)
    job = mf.built(dock, h.RUNS / "job")
    h.check("Hybrid 2D: the job keeps the catchments in the mesh", "exclude_lumped" not in job["grid"] and job["run"].get("model_type") == "hybrid_2d" and "lumped_only" not in job["run"], (list(job["grid"]), job["run"]))
    h.check("Hybrid 2D: the entry is the outlets, the engine's default", "lumped_entry" not in job["hydrology"], job["hydrology"])
    h.check("Hybrid 2D: the entry chosen for Hybrid Lumped is kept for later", hy.lumped_entry.currentData() == "network")

    h.log("=== 7 2D with an HMS project still set: left out of the job, and said")
    header.back_button.click()
    start.cards["2d"].click()
    yield lambda: True
    h.check("the HMS project is still in the dock", hy.folder.filePath() == str(hms))
    values = dock._collect()
    h.check("2D: the HMS project stays out of the values", "hms" not in values and values["model_type"] == "2d")
    h.check("2D: the header says what is not used", "not used" in header.note.text() and header.note.isVisible(), header.note.text())
    h.check("2D: the storm of the HMS project cannot be meant, and that stops the run in words", problems(values) != [], problems(values))

    h.log("=== 8 the type is the model's: saved and read back")
    start_doc = dock.model.collect()
    h.check("the model document holds the type", (start_doc["model_type"], start_doc["show_all"], start_doc["page"]) == ("2d", False, "model"))
    header.back_button.click()
    start.cards["hybrid_lumped"].click()
    hybrid = dock.model.collect()
    dock.model.reset()
    yield lambda: True
    h.check("a new model starts on the start page with no type", dock.pages.currentIndex() == 0 and types.kind is None and not hy.folder.filePath())
    dock.model.apply(hybrid)
    yield lambda: hy.files["basin"].count() > 0
    h.check("the type came back with the model", types.kind == "hybrid_lumped" and dock.pages.currentIndex() == 1 and header.badge.text() == "HYB-L", (types.kind, header.badge.text()))
    h.check("its ticks came back with it", hy.exclude.isChecked() and not hy.exclude.isVisible() and hy.lumped_entry.currentData() == "network")

    h.log("=== 9 a model with no word on its type gets the one it runs as")
    old = {key: value for key, value in hybrid.items() if key not in ("model_type", "page", "show_all")}
    dock.model.reset()
    dock.model.apply(old)
    yield lambda: hy.files["basin"].count() > 0
    h.check("an HMS project with the catchments left out: Hybrid Lumped", types.kind == "hybrid_lumped" and dock.pages.currentIndex() == 1, types.kind)
    old["sections"]["hydrology"]["widgets"]["exclude"] = False
    dock.model.reset()
    dock.model.apply(old)
    h.check("the same with the catchments kept: Hybrid 2D", types.kind == "hybrid_2d", types.kind)
    old["sections"]["hydrology"]["widgets"]["lumped_only"] = True
    dock.model.reset()
    dock.model.apply(old)
    h.check("the HMS way only: Lumped", types.kind == "lumped", types.kind)
    old["sections"]["hydrology"]["widgets"]["folder"] = ""
    dock.model.reset()
    dock.model.apply(old)
    h.check("no lumped part: 2D", types.kind == "2d", types.kind)
    h.check("an HMS folder that is gone leaves no file chosen from it", hy.files["basin"].count() == 0, hy.files["basin"].currentText())

    h.log("=== 10 All sections, no model type: the dock as it was")
    dock.model.reset()
    start.all_button.click()
    yield lambda: True
    h.check("all sections and every Hydrology row", shown(dock) == list(ALL_SECTIONS) and hy.lumped_box.isVisible() and hy.exclude.isVisible())
    h.set_rain_job(dock, ground, "plain", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=False)
    job = mf.built(dock, h.RUNS / "job")
    h.check("the job names no type", "model_type" not in job["run"], job["run"])
    h.check("the header says so in words", header.badge.text() == "ALL" and "names no model type" in header.meaning.text(), header.meaning.text())

    h.log("=== 11 Open a finished run from the start page")
    dock.model.reset()
    start.run_folder.setFilePath(str(h.RUNS / "nothing_here"))
    start.open_run_button.click()
    h.check("a folder with no run: said on the start page", "no run in this folder" in start.message.text() and dock.pages.currentIndex() == 0, start.message.text())
    start.run_folder.setFilePath(str(run))
    start.open_run_button.click()
    yield lambda: True
    h.check("the run's model is in the dock, on the model page", dock.pages.currentIndex() == 1 and types.kind == "2d" and dock.terrain.dx.value() == 30.0, (types.kind, dock.terrain.dx.value()))
    h.check("its results are at hand", dock.results_dir == run and dock.panel.lines_button.isEnabled())

    h.log("=== 12 two things that must not lose a model")
    dock.terrain.dx.setValue(35.0)
    dock.panel.duration.setValue(1.5)
    before = dock.schema
    dock.load_engine()  # what pressing OK in Engine... does
    yield lambda: dock.schema is not before
    h.check("the engine answering again keeps every field", dock.terrain.dx.value() == 35.0 and dock.panel.duration.value() == 1.5 and types.kind == "2d", (dock.terrain.dx.value(), dock.panel.duration.value(), types.kind))
    broken = json.loads(json.dumps(dock.model.collect()))
    broken["sections"]["terrain"]["widgets"]["dx"] = "wide"
    broken["sections"]["simulation"]["widgets"]["duration"] = 2.5
    said = dock.model.apply(broken)
    h.check("a model file edited by hand: the bad section is named", any("1. Terrain" in text and "could not be read" in text for text in said), said)
    h.check("and the other sections still come back", dock.panel.duration.value() == 2.5, dock.panel.duration.value())
    yield lambda: True
