"""W105: the last points of the lumped model through the real dock, on W103's two dock-way scenarios of Block 2.

Each scenario (a model of format 5) is opened, comes up with Basin 3's five dams listed and ticked and the migration's
words; HAT-J4 is added once from the junction list and once by a click on the map beside its HMS icon; the status line
says it; the job the dock writes, as Run writes it, holds the five dams and HAT-J4 and nothing else new; the model saved
(format 6) and opened again writes the same job; a dam unticked writes the four others, a 2D model none. The two jobs
are kept for ``scripts/compare_last_points.py``. Read only on W79, W103 and his HMS project; no 2D solver runs.
"""

import json
from pathlib import Path

W103 = Path(r"D:\Mojtaba\Renardet\Wadi2D\W103 Block 2 scenarios complete")
HERE = Path(__file__).resolve().parent
DATA = HERE / "dock_data"
CASES = (
    ("Hybrid Lumped, dock way", "hybrid_lumped", "hybrid_lumped_last_points"),
    ("Hybrid 2D, dock way", "hybrid_2d", "hybrid_2d_last_points"),
)
DAMS = ["Bidah 03 Reservoir", "Faydh 01 Reservoir", "R5A Reservoir", "R2A Reservoir", "Z4C Reservoir"]
HAT_J4 = "HAT-J4"
HAT_ICON = (427883.48973783385, 2740317.893463373)
MAIN_VENV = Path(r"D:\Mojtaba\Renardet\Wadi2D\.venv\Scripts\python.exe")


def write_job(h, dock, out: Path):
    """The job the dock writes now, as Run writes it. Use: ``job = yield from ...``."""
    made = {}
    values = dock._collect()
    values["output"] = str(out)
    dock._prepare(values, out, lambda path: made.update(job=json.loads(Path(path).read_text(encoding="utf-8"))),
                  lambda text: made.update(error=text), lambda text, _tone="info": None)  # fmt: skip
    yield lambda: made
    h.check(f"the dock writes its job into {out.name}", "job" in made, made.get("error", ""))
    return made.get("job")


def open_dock(h, wait_s: float = 120.0):
    """``h.open_dock`` with a limit on the engine's first answer, and what the dock says if it does not come."""
    import sys
    import time

    sys.path.insert(0, str(h.REPO / "plugin"))
    import wadi2d_qgis
    from qgis.core import QgsApplication
    from qgis.utils import iface
    from wadi2d_qgis import settings

    h.check("plugin from this checkout", str(h.REPO) in wadi2d_qgis.__file__, wadi2d_qgis.__file__)
    venv = h.VENV if h.VENV.is_file() else MAIN_VENV  # a worktree has no venv of its own; engine.py runs this checkout
    settings.set_engine_text(f'"{venv}" "{h.P / "engine.py"}"')
    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    h.current[0] = dock
    start = time.monotonic()
    yield lambda: dock.schema is not None or time.monotonic() - start > wait_s
    h.check("engine found", dock.schema is not None, dock.engine_label.text())
    if dock.schema is None:
        log = QgsApplication.messageLog()
        h.log(f"engine label: {dock.engine_label.text()}; message log: {log}")
        raise RuntimeError("no engine")
    if dock.types.page == "start":
        dock.start_page.all_button.click()
    return dock


def scenario(h):
    from qgis.core import QgsApplication

    seen = []
    QgsApplication.messageLog().messageReceived.connect(lambda text, tag, level: seen.append(f"[{tag}] {text}"))
    try:
        dock = yield from open_dock(h)
    finally:
        for text in seen:
            h.log(f"message: {text[:600]}")
    from qgis.core import QgsPointXY
    from wadi2d_qgis import model_doc
    from wadi2d_qgis.last_point_rows import DAM, JUNCTION

    DATA.mkdir(exist_ok=True)
    hyd = dock.hydrology
    table = hyd.last_points
    report = {}
    for title, kind, folder in CASES:
        h.log(f"=== {title}")
        source = W103 / "scenarios" / f"{title}.wadi2d.json"
        h.check(f"{title}: W103's scenario is format 5", json.loads(source.read_text(encoding="utf-8"))["version"] == 5)
        dock.panel.folder.setFilePath(str(W103))
        words = dock.model.open_scenario(str(source))
        dock.types.choose(kind)
        h.log(f"{title}: opened, words: {words}")
        said = " ".join(words or []) if isinstance(words, list) else str(words or "")
        expect = model_doc.LAST_POINTS_NETWORK if kind == "hybrid_lumped" else model_doc.LAST_POINTS_CURVE
        h.check(f"{title}: the migration says what moves", expect[:60] in said or expect[:60] in dock.model_bar.message.text(),
                dock.model_bar.message.text()[:300])  # fmt: skip
        rows = table.rows()
        h.check(f"{title}: Basin 3's five dams listed and ticked", sorted(r[0] for r in rows) == sorted(DAMS) and all(r[1] == DAM and r[2] for r in rows), rows)
        h.check(f"{title}: HAT-J4 offered among the junctions", HAT_J4 in table.junctions, len(table.junctions))
        h.check(f"{title}: as it stands nothing is written", hyd.last_points_value() is None)
        table.junction.setCurrentText(HAT_J4)
        table.add_button.click()
        rows = table.rows()
        h.check(f"{title}: Add a junction adds HAT-J4", rows[-1] == (HAT_J4, JUNCTION, True), rows[-1])
        table.table.selectRow(len(rows) - 1)
        table.drop_button.click()
        h.check(f"{title}: Remove junction takes it out", HAT_J4 not in [r[0] for r in table.rows()])
        table.place_button.setChecked(True)
        h.check(f"{title}: Pick on the map takes the canvas", dock.iface.mapCanvas().mapTool() is dock.last_point_clicks.tool)
        dock.last_point_clicks._clicked(QgsPointXY(HAT_ICON[0] + 40.0, HAT_ICON[1] - 30.0))
        rows = table.rows()
        h.check(f"{title}: a click beside its icon adds HAT-J4", rows[-1] == (HAT_J4, JUNCTION, True) and not table.place_button.isChecked(), (rows[-1], table.note.text()))
        h.check(f"{title}: and gives the tool back", dock.iface.mapCanvas().mapTool() is not dock.last_point_clicks.tool)
        status = hyd.standing(kind)
        h.check(f"{title}: the status line says it", "the lumped model ends at 5 dams + HAT-J4" in status.words, status.words)
        words_4b = dock.reduction.lumped.note.text() if hasattr(dock.reduction.lumped, "note") else ""
        h.log(f"{title}: 4b reads: {words_4b[:200]}")
        dock.panel.folder.setFilePath(str(DATA))
        path = dock.model.save_scenario(title)
        h.check(f"{title}: saved as a scenario of format 6", path is not None and json.loads(Path(path).read_text(encoding="utf-8"))["version"] == 6, str(path))
        job = yield from write_job(h, dock, DATA / "rebuilt" / folder)
        if job is None:
            continue
        h.check(f"{title}: the job holds the five dams, in the basin's order, and HAT-J4", job["hydrology"].get("last_points") == [*table.dams, HAT_J4] and sorted(table.dams) == sorted(DAMS), job["hydrology"].get("last_points"))
        before = json.loads((W103 / "rebuilt" / ("hybrid_lumped_dock_way" if kind == "hybrid_lumped" else "hybrid_2d_dock_way") / "job.json").read_text(encoding="utf-8"))
        changed = sorted(k for k in set(job["hydrology"]) | set(before["hydrology"]) if job["hydrology"].get(k) != before["hydrology"].get(k))
        h.check(f"{title}: in hydrology only the last points differ from W103's job", changed == ["last_points"], changed)
        dock.model.open_scenario(str(path))
        dock.types.choose(kind)
        again = yield from write_job(h, dock, DATA / "checks" / f"{folder}_opened_again")
        h.check(f"{title}: opened again, the same hydrology", again is not None and again["hydrology"] == job["hydrology"])
        first = table.table.item(0, 2)
        first.setCheckState(0)  # Qt.Unchecked
        first_dam = table.table.item(0, 0).text()
        h.check(f"{title}: a dam unticked ({first_dam}) writes the others", hyd.last_points_value() == [d for d in table.dams if d != first_dam] + [HAT_J4], hyd.last_points_value())
        first.setCheckState(2)  # Qt.Checked
        report[title] = {"scenario": str(path), "job": str(DATA / "rebuilt" / folder / "job.json"), "status": status.words}
    dock.types.choose("2d")
    h.check("a 2D model carries no last point", "last_points" not in dock._collect())
    (DATA / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    h.check("the report written", (DATA / "report.json").is_file())
