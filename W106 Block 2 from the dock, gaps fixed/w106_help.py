"""What the W106 dock scenarios share (copied from W104's, its paths and three steps changed). Not a scenario: each loads it by path (``helper(h)``).

Every input of the model goes through the dock's own widgets; this module only loads the designer's raw layers into
the project (as a user drags files in), clicks, waits, times each step, saves pictures and the QGIS project.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

W106 = Path(__file__).resolve().parent
INPUTS = W106 / "inputs"
RUNS = W106 / "runs"
LOGS = W106 / "logs"
PROJECT = W106 / "Block2_from_the_dock_W106.qgz"
NUMBERS = json.loads((INPUTS / "storm_numbers.json").read_text(encoding="utf-8"))
MODELS = {"lumped": "Lumped", "2d": "2D", "hybrid_lumped": "HybridLumped", "hybrid_2d": "Hybrid2D"}
"""Each model type's output folder under runs/: one model group in QGIS each, and its own generated basin."""
PATTERN_NAME = "FM 10-1000yr"
CURVE_NAME = "ARF FM"


def helper(h, name="w106_help"):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, Path(h.SCENARIO).parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Steps:
    """Each step's wall time and what the dock said, into logs/<session>_steps.json as it goes."""

    def __init__(self, h, session: str) -> None:
        self.h, self.session = h, session
        self.rows: list[dict] = []
        self.started: dict[str, float] = {}
        LOGS.mkdir(exist_ok=True)
        self.path = LOGS / f"{session}_steps.json"

    def begin(self, label: str) -> None:
        self.started[label] = time.monotonic()
        self.h.log(f"STEP {label}")

    def end(self, label: str, said: str = "", **more) -> None:
        took = time.monotonic() - self.started.pop(label, time.monotonic())
        self.rows.append({"step": label, "seconds": round(took, 1), "said": said[:2000], **more})
        self.h.log(f"STEP DONE {label} {took:.1f} s: {said[:300]}")
        self.path.write_text(json.dumps(self.rows, indent=1), encoding="utf-8")


def limits(h, hours: float = 6.0) -> None:
    h.TOTAL_LIMIT = hours * 3600.0
    h.STEP_LIMIT = hours * 3600.0


def add_vector(h, name: str, title: str, crs):
    """The drawn layer as a user drags it in. The outflow lines are a working copy under runs/inputs, since the
    dock's Add outflow lines there writes into the Boundaries layer (W106 gap 9) and inputs/ stays as drawn."""
    import shutil

    from qgis.core import QgsProject, QgsVectorLayer

    path = INPUTS / f"{name}.gpkg"
    if name == "outflow_lines":
        work = RUNS / "inputs" / "outflow_lines.gpkg"
        if not work.is_file():
            work.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, work)
        path = work
    layer = QgsVectorLayer(str(path), title, "ogr")
    layer.setCrs(crs)
    QgsProject.instance().addMapLayer(layer)
    return layer


def load_inputs(h) -> dict:
    """The designer's raw layers, dragged into an empty project: his DEM, CN and Manning rasters, and what he drew."""
    from qgis.core import QgsProject, QgsRasterLayer

    project = QgsProject.instance()
    dem = QgsRasterLayer(NUMBERS["dem"], "GGC_2_MERGE_HDSM (0.5 m)")
    project.addMapLayer(dem)
    crs = dem.crs()
    project.setCrs(crs)
    cn = QgsRasterLayer(NUMBERS["cn_raster"], "CN_Include_Hill_Area")
    manning = QgsRasterLayer(NUMBERS["manning_raster"], "Manning n, hills 0.1 (W79)")
    for layer in (cn, manning):
        project.addMapLayer(layer)
    out = {"dem": dem, "cn": cn, "manning": manning, "crs": crs}
    for key, title in (
        ("rough_outline", "Rough outline of Block 2"), ("outflow_lines", "Outflow lines"),
        ("crest_lines", "Dam crest lines"), ("spillways", "Dam spillways"), ("dam_lines", "Dam lines"),
    ):  # fmt: skip
        out[key] = add_vector(h, key, title, crs)
    h.log("inputs: " + ", ".join(f"{k} valid={v.isValid()}" for k, v in out.items() if k != "crs"))
    return out


def find_layer(title_start: str):
    from qgis.core import QgsProject

    found = [layer for layer in QgsProject.instance().mapLayers().values() if layer.name().startswith(title_start)]
    return found[-1] if found else None


def layers_by_title(title_start: str) -> list:
    from qgis.core import QgsProject

    return [layer for layer in QgsProject.instance().mapLayers().values() if layer.name().startswith(title_start)]


def pick(combo, key) -> bool:
    index = combo.findData(key)
    combo.setCurrentIndex(index)
    return index >= 0


def pick_text(combo, text) -> bool:
    index = combo.findText(text)
    combo.setCurrentIndex(index)
    return index >= 0


def card(dock, kind: str) -> None:
    """The start page's card of a model type, as a click on it; from the model page, Types first."""
    if dock.types.page != "start":
        dock.header.back_button.click()
    dock.start_page.cards[kind].click()


def big_shot(h, dock, name, size=(460, 1100), open_only=None):
    """The dock's frame at the width of a real dock, the one section open when asked (W101's way)."""
    from qgis.PyQt.QtWidgets import QApplication

    if open_only is not None:
        for section in dock.sections:
            section.setCollapsed(section.key != open_only)
    dock.status_links.refresh()
    if open_only is not None:
        QApplication.processEvents()
        dock.cards[open_only].grab().save(str(h.P / f"widget_{name}_card.png"))
    frame = dock.widget()
    held = frame.size()
    frame.resize(*size)
    QApplication.processEvents()
    page = dock.pages.currentWidget()
    if hasattr(page, "widget") and page.widget() is not None:
        page.widget().resize(page.viewport().width(), page.widget().height())
        QApplication.processEvents()
    if open_only is not None and dock.types.page == "model":
        dock.scroll.verticalScrollBar().setValue(max(dock.cards[open_only].y() - 8, 0))
    frame.grab().save(str(h.P / f"widget_{name}.png"))
    frame.resize(held)
    QApplication.processEvents()


def render_map(h, name, layers, extent_layer=None, size=(1100, 900)):
    """A picture of the map, drawn off the screen: the throwaway window is minimized."""
    from qgis.core import QgsMapRendererSequentialJob, QgsMapSettings, QgsProject
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor

    layers = [layer for layer in layers if layer is not None and layer.isValid()]
    if not layers:
        return None
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setDestinationCrs(QgsProject.instance().crs())
    settings.setOutputSize(QSize(*size))
    settings.setBackgroundColor(QColor("white"))
    extent = (extent_layer or layers[-1]).extent()
    extent.scale(1.05)
    settings.setExtent(extent)
    job = QgsMapRendererSequentialJob(settings)
    job.start()
    job.waitForFinished()
    path = h.P / f"map_{name}.png"
    job.renderedImage().save(str(path))
    return path


def wait_query(attr_owner, attr: str, button):
    """Until the engine query an object holds is done and its button is back."""
    return lambda: getattr(attr_owner, attr) is None and button.isEnabled()


def save_project(h) -> None:
    from qgis.core import QgsProject

    ok = QgsProject.instance().write(str(PROJECT))
    h.check(f"project saved: {PROJECT.name}", ok)


def read_project(h) -> None:
    """The project as saved; a layer whose file has moved is left unavailable, said in the log, never a dialog
    (QGIS's own would wait for a hand on a minimized window)."""
    from qgis.core import QgsProject, QgsProjectBadLayerHandler

    class Quiet(QgsProjectBadLayerHandler):
        def handleBadLayers(self, layers) -> None:
            h.log(f"unavailable layers left as they are: {len(layers)}")

    held = Quiet()
    h.QUIET_HANDLER = held  # kept alive for the session
    QgsProject.instance().setBadLayerHandler(held)
    ok = QgsProject.instance().read(str(PROJECT))
    h.check(f"project read: {PROJECT.name}", ok, str(PROJECT))


def save_scenario(h, dock, name: str) -> Path | None:
    dock.model_bar.scenario_name.setText(name)
    dock.model_bar.save_button.click()
    found = Path(dock.panel.folder.filePath()) / "scenarios"
    paths = sorted(found.glob(f"{name}*.json")) if found.is_dir() else []
    h.check(f"scenario {name} saved", bool(paths), dock.model_bar.message.text()[:300])
    return paths[0] if paths else None


def job_of(dock) -> dict:
    """The job the dock would write now, read back from a scratch folder (never a run's)."""
    import shutil
    import tempfile

    from wadi2d_qgis.job_builder import build_job

    out = Path(tempfile.mkdtemp(prefix="w106_job_"))
    try:
        return json.loads(json.dumps(build_job({**dock._collect(), "output": str(out)}, out)))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def problems_now(dock) -> list[str]:
    from wadi2d_qgis.job_builder import problems

    values = dock._collect()
    return problems(values)


def type_storm(h, dock) -> None:
    """Data tables: the 24 h pattern and the ARF table of his met file, typed (pasted) row by row; Storm: 251 mm in
    24 h on that pattern."""
    tables, storm = dock.tables, dock.storm
    tables.setCollapsed(False)
    pick(tables.which, "patterns")
    tables.new_button.click()
    tables.name_edit.setText(PATTERN_NAME)
    tables.rename_button.click()
    pick(tables.time_units, "percent")
    pick(tables.form_kind, "cumulative")
    pattern = NUMBERS["pattern"]
    tables.pairs.set_rows(list(zip(pattern["time_percent"], pattern["depth_percent"], strict=True)))
    held = tables.store["patterns"].get(PATTERN_NAME, {})
    h.check("pattern typed into Data tables", len(held.get("time", [])) == len(pattern["time_percent"]), (len(held.get("time", [])), tables.problem.text()))
    pick(tables.which, "arf_curves")
    tables.new_button.click()
    tables.name_edit.setText(CURVE_NAME)
    tables.rename_button.click()
    arf = NUMBERS["arf_fm"]
    pick(tables.below, bool(arf["reduces_below_table"]))
    tables.pairs.set_rows(list(zip(arf["areas_km2"], arf["factors"], strict=True)))
    held = tables.store["arf_curves"].get(CURVE_NAME, {})
    h.check("ARF FM typed into Data tables", held.get("factors") == arf["factors"], (held.get("factors"), tables.problem.text()))
    storm.setCollapsed(False)
    pick(storm.kind, "depth")
    storm.depth_mm.setValue(NUMBERS["depth_mm"])
    storm.depth_hours.setValue(NUMBERS["duration_h"])
    ok = pick(storm.depth_pattern, f"table:{PATTERN_NAME}")
    h.check("Storm: 251 mm in 24 h on the pattern", ok and storm.depth_mm.value() == 251.0, storm.depth_pattern.currentText())


def set_reduction(h, dock, lumped: str | None, grid_area: float | None) -> None:
    """Area reduction: the lumped part as the curve (or none), the 2D part read on the curve at one area."""
    arf = dock.reduction
    arf.setCollapsed(False)
    if lumped is not None:
        pick(arf.lumped.form, lumped)
        pick(arf.lumped.curve, CURVE_NAME)
    if grid_area is not None:
        pick(arf.grid.form, "area")
        pick(arf.grid.curve, CURVE_NAME)
        arf.grid.area.setValue(grid_area)
    h.log(f"reduction: lumped {arf.lumped.form.currentData()} {arf.lumped.note.text()[:200]} | 2D {arf.grid.form.currentData()} {arf.grid.factor.text()[:200]}")


def set_simulation(h, dock, backend: str = "gpu") -> None:
    sim = dock.simulation
    sim.setCollapsed(False)
    sim.duration.setValue(NUMBERS["duration_hours"])
    sim.lumped_step.setValue(NUMBERS["lumped_step_min"])
    sim.maps.setCurrentIndex(0)  # every 15 minutes, for design work
    pick(sim.backend, backend)
    h.log(f"simulation: {sim.duration.value()} h, lumped {sim.lumped_step.value()} min, maps {sim.maps.currentText()}, {sim.backend.currentText()}")


def set_terrain(h, dock, lay: dict) -> None:
    t = dock.terrain
    t.setCollapsed(False)
    t.dem.setLayer(lay["dem"])
    t.dx.setValue(NUMBERS["dx"])
    pick(t.manning_form, "grid")
    t.manning.raster.setLayer(lay["manning"])
    t.manning.box.setValue(NUMBERS["manning"])
    t.fill_pits.setChecked(True)
    h.log(f"terrain: {t.dem.currentLayer().name()}, {t.dx.value()} m, Manning {t.manning_form.currentText()} {t.manning.raster.currentLayer().name()} / {t.manning.value()}, pits {t.fill_pits.isChecked()}")


def set_boundaries(h, dock, lay: dict) -> None:
    """The four outflow lines, each typed normal depth with its slope in the table."""
    b = dock.boundaries
    b.setCollapsed(False)
    b.layer.setLayer(lay["outflow_lines"])
    slopes = NUMBERS["slopes"]
    from wadi2d_qgis.sections.boundaries import KIND_COLUMN, VALUE_COLUMN

    for number, row in enumerate(b.rows):
        kind = b.table.cellWidget(number, KIND_COLUMN)
        kind.setCurrentText("normal")
        value = b.table.cellWidget(number, VALUE_COLUMN)
        value.setValue(slopes.get(row.label, ADDED_SLOPE))  # a line the dock added (gap 9): the Fizh branch's 0.005
    words = [(row.label, row.kind, row.value) for row in b.rows]
    drawn = [r for r in b.rows if r.label in slopes]
    h.check("his four outflow lines, normal depth at their slopes", len(drawn) == 4 and all(r.kind == "normal" and abs(r.value - slopes[r.label]) < 1e-9 for r in drawn), words)
    h.log(f"boundary rows: {words}")


ADDED_SLOPE = 0.005
"""The slope typed for an outflow line the dock added where a stream leaves the completed domain: W79's Fizh branch and
North stream lines' (storm_numbers.json)."""


def set_cn(h, dock, lay: dict, fill: float | None) -> None:
    """Hydrology: his raw CN grid, holes and all, and beside it the CN of its holes (W106 gap 1), or none."""
    hyd = dock.hydrology
    hyd.setCollapsed(False)
    hyd.cn.raster.setLayer(lay["cn"])
    h.check("the CN value stays open beside the CN grid", hyd.cn.box.isEnabled(), hyd.cn.box.specialValueText())
    hyd.cn.box.setValue(fill if fill is not None else hyd.cn.box.minimum())
    h.log(f"curve number: grid {hyd.cn.raster.currentLayer().name()}, value {hyd.cn.box.value()} ({hyd.cn.box.text()})")


def set_structures(h, dock, lay: dict) -> None:
    s = dock.structures
    s.setCollapsed(False)
    s.layers["crest_line"].setLayer(lay["crest_lines"])
    s.fields["crest_line"]["crest_z"].setField("z")
    s.layers["spillway"].setLayer(lay["spillways"])
    s.fields["spillway"]["crest_z"].setField("z")
    s.fields["spillway"]["coefficient"].setField("c")
    s.fields["spillway"]["length"].setField("length")
    p = dock.points
    p.setCollapsed(False)
    p.layer.setLayer(lay["dam_lines"])
    p.name.setField("name")
    h.log(f"structures: {s.standing().words[:200]} | points: {p.standing().words[:200]}")


def run_and_time(h, dock, steps: Steps, label: str, limit_h: float = 3.0):
    """Press Run; wait for the end (the dock idle, its layers loaded). The engine's own stages come from the run
    folder afterwards."""
    steps.begin(label)
    started = time.time()
    dock.panel.run_button.click()  # without an HMS project the job is written and the engine started in the click
    yield lambda: True
    if dock.run is None:
        steps.end(label, dock.panel.message.text(), refused=True)
        return None
    yield lambda: dock.run is None or dock.run.out_dir is not None
    folder = Path(dock.run.out_dir) if dock.run is not None else Path(dock.results_dir)
    seen: dict[str, float] = {}
    idle = h.idle(dock, limit_h * 3600.0)
    offset = [0]

    def watch() -> bool:
        """The wall time each kind of engine event first shows in progress.jsonl: the stages of the run."""
        path = folder / "progress.jsonl"
        if path.is_file():
            with path.open(encoding="utf-8") as f:
                f.seek(offset[0])
                for line in f:
                    if not line.endswith("\n"):
                        break
                    offset[0] += len(line.encode("utf-8"))
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    key = ev.get("ev", "?") + (f":{ev['stage']}" if ev.get("stage") else "")
                    seen.setdefault(key, round(time.time() - started, 1))
        return idle()

    yield watch
    watch()
    (LOGS / f"{steps.session}_{folder.name}_stages.json").write_text(json.dumps(seen, indent=1), encoding="utf-8")
    steps.end(label, dock.panel.message.text(), folder=str(folder), started_epoch=started, ended_epoch=time.time(), first_seen_s=seen)
    return folder
