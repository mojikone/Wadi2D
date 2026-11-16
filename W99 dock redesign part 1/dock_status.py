"""W99 step 3 through the real dock: every section is a card with its status in words, the step strip over them, the
footer under them with Check and run.

What a user sees while filling a model in: a status that follows the widgets within the second, the words that say what
is missing, a step that opens its section, and Check and run, which refuses in words and then runs. Also the guard of
the engine's settings: a section that cannot take them is named and the others go on.
"""

import importlib.util
import json
from pathlib import Path


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


def scenario(h):
    mf = helper(h)
    ground = h.Bidah()
    extra = mf.extra_layers(h, ground)
    dock = yield from h.open_dock(all_sections=False)
    from wadi2d_qgis import look
    from wadi2d_qgis.section_status import MISSING, OPTIONAL, READY, STATE_MARKS, STATE_WORDS

    links, strip, footer, cards = dock.status_links, dock.strip, dock.footer, dock.cards
    words = set(STATE_WORDS.values())

    def state(key):
        return links.refresh()[key]

    h.log("=== 1 the model page: a card a section, each with its status in words")
    dock.start_page.cards["2d"].click()
    yield lambda: True
    statuses = links.refresh()
    h.check("the light palette on a light theme", not look.is_dark(dock.palette()) and look.LIGHT.card in dock.widget().styleSheet())
    h.check("every section sits in a card", set(cards) == {s.key for s in dock.sections} and all(cards[s.key].section is s for s in dock.sections))
    h.check("every section answers with a state and words", all(st.state in (READY, OPTIONAL, MISSING) and st.words for st in statuses.values()), {k: v for k, v in statuses.items() if not v.words})
    h.check("every card's pill says its state in a word", all(card.pill.text() in words and card.pill.isVisible() for card in cards.values()), [c.pill.text() for c in cards.values()])
    h.check("a closed card shows its words under the title", all(c.closed_words.isVisible() and c.closed_words.text() == c.status.words for c in cards.values() if c.section.isCollapsed()))
    h.check("an open card shows its words as its first row", all(c.open_words.isVisible() and c.open_words.text() == c.status.words for c in cards.values() if not c.section.isCollapsed()))
    h.check("the sections are the boxes they were: title and arrow their own", dock.terrain.title() == "1. Terrain" and dock.panel.title() == "8. Run")
    h.log(f"statuses: { {k: (v.state, v.words) for k, v in statuses.items()} }")
    h.check("Terrain is ready with the DEM it found", statuses["terrain"].state == READY and "DEM terrain" in statuses["terrain"].words, statuses["terrain"])
    h.check("Run misses its output folder, in words", statuses["run"] == (MISSING, "Choose an output folder."), statuses["run"])
    h.check("Storm misses its rain, in words", statuses["storm"] == (MISSING, "Set the rain and how many hours it lasts."), statuses["storm"])
    h.check("nothing optional is called missing", all(statuses[k].state == OPTIONAL for k in ("mesh", "structures", "boundaries", "points", "gauges", "study")), {k: statuses[k].state for k in statuses})

    h.log("=== 2 the step strip and the footer")
    shown = [s.key for s in dock.sections]
    h.check("one step a section, in the dock's order", [k for k in strip.steps if strip.steps[k].isVisible()] == shown, list(strip.steps))
    h.check("a step carries its name and a mark, not colour alone", all(strip.steps[k].text().split(" ", 1)[0] == STATE_MARKS[statuses[k].state] and len(strip.steps[k].text()) > 3 for k in shown), [b.text() for b in strip.steps.values()])
    h.check("a step says its status in words to a pointer and a screen reader", all(STATE_WORDS[statuses[k].state] in strip.steps[k].toolTip() and strip.steps[k].accessibleName() == strip.steps[k].toolTip() for k in shown), strip.steps["run"].toolTip())
    h.check("the footer counts what is missing, and names it", footer.needs.text() == "2 sections need you before running: Storm, Run", footer.needs.text())
    h.check("Check and run is there, in the footer", footer.run_button.text() == "Check and run" and footer.isVisible() and footer.run_button.isEnabled())
    big_shot(h, dock, "status_2d_start")

    h.log("=== 3 the status follows the widgets")
    h.set_rain_job(dock, ground, "status", dx=30.0, rain=40.0, hours=0.5, sim_hours=0.75, pixels=False)
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    statuses = links.refresh()
    h.check("the folder chosen: Run is ready", statuses["run"].state == READY and "Into status" in statuses["run"].words, statuses["run"])
    h.check("the footer says so", footer.needs.text() == "No section is missing anything", footer.needs.text())
    h.check("Terrain says the cell and the domain", "cell 30 m" in statuses["terrain"].words and "domain domain bidah" in statuses["terrain"].words, statuses["terrain"].words)
    h.check("Storm says the rain", statuses["storm"] == (READY, "Constant rain 40 mm/h for 0.5 h"), statuses["storm"])
    h.check("Boundaries says its lines", statuses["boundaries"].state == READY and "2 lines" in statuses["boundaries"].words, statuses["boundaries"])
    dock.boundaries.table.cellWidget(1, 1).setCurrentText("flow")
    h.check("a flow line with no hydrograph: missing, and which line", state("boundaries") == (MISSING, "Boundary line 2: a flow line needs its hydrograph file in the table."), state("boundaries"))
    h.check("its card's border and pill follow", cards["boundaries"].property("status") == MISSING and cards["boundaries"].pill.text() == "Missing")
    dock.boundaries.table.cellWidget(1, 1).setCurrentText("normal")
    dock.storm.kind.setCurrentIndex(dock.storm.kind.findData("hypothetical"))
    dock.storm.design_depth.setValue(120.0)
    dock.storm.design_hours.setValue(6.0)
    h.check("a design storm with no pattern: missing, in the job check's own words", state("storm").state == MISSING and "design pattern" in state("storm").words, state("storm"))
    dock.storm.pattern.set_rows([(0.0, 0.0), (100.0, 100.0)])
    h.check("with its pattern: ready, and what it is", state("storm") == (READY, "Design storm 120 mm in 6 h \N{MIDDLE DOT} no area reduction"), state("storm"))
    dock.storm.kind.setCurrentIndex(dock.storm.kind.findData("single"))
    dock.structures.layers["crest_line"].setLayer(ground.lines)
    h.check("crest lines with no elevation: missing", state("structures").state == MISSING and "elevation" in state("structures").words, state("structures"))
    dock.structures.layers["crest_line"].setLayer(extra["crests"])
    dock.structures.fields["crest_line"]["crest_z"].setField("crest_z")
    h.check("with their field: ready", state("structures") == (READY, "Crest lines"), state("structures"))
    dock.structures.layers["crest_line"].setLayer(None)
    dock.structures.layers["wall"].setLayer(ground.lines)
    h.check("a wall needs no elevation: ready", state("structures") == (READY, "Walls"), state("structures"))
    dock.structures.layers["wall"].setLayer(None)
    dock.mesh.enabled.setChecked(True)
    dock.mesh.corridors.setChecked(True)
    h.check("the mesh and the corridors together: missing", state("mesh").state == MISSING and "untick" in state("mesh").words, state("mesh"))
    dock.mesh.corridors.setChecked(False)
    dock.mesh.enabled.setChecked(False)
    dock.gauges.add_row("flow")
    h.check("a gauge with no record: missing, by name", state("gauges") == (MISSING, "Gauge G1 needs its record file."), state("gauges"))
    dock.gauges.gauges.rows.clear()
    dock.gauges.gauges._show()
    h.check("back to optional with no gauge", state("gauges").state == OPTIONAL)

    h.log("=== 4 the type has its say in the status")
    dock.header.back_button.click()
    dock.start_page.cards["lumped"].click()
    yield lambda: True
    statuses = links.refresh()
    h.check("Lumped with no network: Hydrology is missing, in words", statuses["hydrology"].state == MISSING and "Lumped model needs its lumped catchments" in statuses["hydrology"].words, statuses["hydrology"])
    visible = [k for k in strip.steps if strip.steps[k].isVisible()]
    h.check("the strip shows the type's sections only", "mesh" not in visible and "boundaries" not in visible and "hydrology" in visible, visible)
    h.check("the footer counts only what shows", footer.needs.text() == "1 section needs you before running: Hydrology", footer.needs.text())
    big_shot(h, dock, "status_lumped_missing")
    dock.header.back_button.click()
    dock.start_page.cards["2d"].click()
    yield lambda: True
    h.check("2D again: nothing missing", links.refresh() and footer.needs.text() == "No section is missing anything", footer.needs.text())

    h.log("=== 5 a step opens its section")
    for section in dock.sections:
        section.setCollapsed(True)
    strip.steps["storm"].click()
    yield lambda: True
    h.check("the step's section is open, the others stay closed", not dock.storm.isCollapsed() and dock.terrain.isCollapsed() and dock.panel.isCollapsed())
    h.check("the step is marked as the one in hand", strip.steps["storm"].property("current") == "true" and strip.steps["terrain"].property("current") == "false")
    h.check("the open card shows its words under its title", cards["storm"].open_words.isVisible() and not cards["storm"].closed_words.isVisible() and cards["storm"].open_words.text() == statuses["storm"].words)
    yield lambda: dock.scroll.verticalScrollBar().value() > 0 or dock.scroll.verticalScrollBar().maximum() == 0
    big_shot(h, dock, "status_2d_ready")

    h.log("=== 6 Check and run: refuses in words, then runs")
    dock.storm.rain.setValue(0.0)
    h.check("no rain: Storm is missing", state("storm") == (MISSING, "Set the rain and how many hours it lasts."), state("storm"))
    footer.run_button.click()
    yield lambda: True
    h.check("Check and run opens Run and says what stops it", not dock.panel.isCollapsed() and "Set the rain" in dock.panel.message.text() and dock.run is None, dock.panel.message.text())
    dock.storm.rain.setValue(40.0)
    links.refresh()
    footer.run_button.click()
    yield lambda: dock.run is not None
    links.refresh()
    h.check("while it runs the footer's button waits, as Run's does", not footer.run_button.isEnabled() and not dock.panel.run_button.isEnabled())
    yield h.idle(dock)
    run = h.RUNS / "status"
    done = h.events(run, "done")
    h.check("the run started from the footer finished", bool(done) and done[-1].get("code") == 0, dock.panel.message.text()[:200])
    links.refresh()
    h.check("and the button is back", footer.run_button.isEnabled())
    job = json.loads((run / "job.json").read_text(encoding="utf-8"))
    h.check("the job is the 2D model's", job["run"].get("model_type") == "2d" and job["grid"]["dx"] == 30.0, job["run"])

    h.log("=== 7 a section that cannot take the engine's settings is named, and the others go on")
    dock.terrain.dx.setValue(35.0)

    def broken(_schema):
        raise FileNotFoundError("the basin file is gone")

    whole = dock.hydrology.apply_schema
    dock.hydrology.apply_schema = broken
    before = dock.schema
    dock.load_engine()
    yield lambda: dock.schema is not before
    said = dock.engine_label.text()
    h.log(f"engine line: {said}")
    h.check("the section is named with the error's own words", "3. Hydrology" in said and "the basin file is gone" in said and said.startswith("Engine ready."), said)
    h.check("the model was kept all the same", dock.terrain.dx.value() == 35.0 and dock.types.kind == "2d", dock.terrain.dx.value())
    h.check("the dock is ready to run", dock.panel.run_button.isEnabled() and footer.run_button.isEnabled())
    dock.hydrology.apply_schema = whole
    before = dock.schema
    dock.load_engine()
    yield lambda: dock.schema is not before
    h.check("with the section whole again the line is plain", dock.engine_label.text() == "Engine ready.", dock.engine_label.text())

    h.log("=== 8 a section's saved state is its own widgets, whatever its attributes lead to")
    from wadi2d_qgis.suggest_lines import Suggester

    before_state = dock.mesh.state()
    dock.mesh.suggester = Suggester(dock)  # what Suggest breaklines leaves on the Mesh section: it points at the dock
    after_state = dock.mesh.state()
    h.check("a helper that points back at the dock adds nothing to the Mesh section's state", after_state == before_state, sorted(set(after_state["widgets"]) - set(before_state["widgets"]))[:5])
    whole = dock.model.collect()
    paths = {key: set(section["widgets"]) for key, section in whole["sections"].items()}
    h.check("no widget is saved by two sections", sum(len(found) for found in paths.values()) == len(set().union(*[{(key, path) for path in found} for key, found in paths.items()])) and "rain" not in paths["hydrology"] and "start" not in paths["storm"] and "duration" not in paths["run"], {key: len(found) for key, found in paths.items()})
    h.check("the model is still kept, and a run can still save its copy", dock.model.keep() is None and not dock.model._said, dock.model._said)
    yield lambda: True
