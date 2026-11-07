# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless smoke test on QGIS's own Python: the real dock, the real process wrapper, the fake engine.

Started by ``test_smoke_qgis.py`` through ``python-qgis-ltr.bat`` with ``QT_QPA_PLATFORM=offscreen``. Arguments:
the engine's Python (the project venv, so that QGIS's environment really has to be cleaned for it to start).
Prints ``SMOKE PASSED`` as its last line. Settings go to a temporary profile.
"""

from __future__ import annotations

import faulthandler
import importlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[1] / "plugin"), str(HERE), str(HERE.parents[1] / "tools")]
faulthandler.enable()

WORK = Path(tempfile.mkdtemp(prefix="wadi2d_smoke_"))
os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(WORK / "profile")
os.environ["WADI2D_FAKE_STEP_S"] = "0.08"

import fake_engine  # noqa: E402
from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas  # noqa: E402
from qgis.PyQt.QtCore import QCoreApplication  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow  # noqa: E402

app = QgsApplication([], True)
app.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
app.initQgis()

import wadi2d_qgis  # noqa: E402
from wadi2d_qgis import settings  # noqa: E402
from wadi2d_qgis.job_builder import problems  # noqa: E402
from wadi2d_qgis.protocol import PROGRESS_FILE, STOP_FILE, pid_alive, read_run_info  # noqa: E402

UTM = QgsCoordinateReferenceSystem("EPSG:32640")
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
PROJECT = QgsProject.instance()


class Iface:
    """The few calls the plugin makes on QGIS's interface."""

    def __init__(self) -> None:
        self.window = QMainWindow()
        self.canvas = QgsMapCanvas(self.window)
        self.window.setCentralWidget(self.canvas)
        self.canvas.setDestinationCrs(UTM)
        self.icons: list = []
        self.menu: list = []

    def mainWindow(self):
        return self.window

    def mapCanvas(self):
        return self.canvas

    def addToolBarIcon(self, action):
        self.icons.append(action)

    def removeToolBarIcon(self, action):
        self.icons.remove(action)

    def addPluginToMenu(self, _menu, action):
        self.menu.append(action)

    def removePluginMenu(self, _menu, action):
        self.menu.remove(action)

    def addDockWidget(self, area, dock):
        self.window.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.window.removeDockWidget(dock)


def say(text: str) -> None:
    print(f"ok: {text}", flush=True)


def check(condition, text: str) -> None:
    if not condition:
        raise AssertionError(text)
    say(text)


def pump(condition, timeout: float = 30.0, what: str = "a condition") -> None:
    limit = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > limit:
            raise TimeoutError(f"gave up waiting for {what}")
        QCoreApplication.processEvents()
        time.sleep(0.005)


def mode(name: str) -> None:
    os.environ["WADI2D_FAKE_MODE"] = name


def to_wgs84(x: float, y: float) -> QgsPointXY:
    return QgsCoordinateTransform(UTM, WGS84, PROJECT).transform(QgsPointXY(x, y))


def line_layer(name: str, fields: str, points, crs="EPSG:32640", attributes=None, kind="LineString"):
    layer = QgsVectorLayer(f"{kind}?crs={crs}{fields}", name, "memory")
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPolylineXY(points) if isinstance(points, list) else points)
    if attributes:
        feature.setAttributes(attributes)
    layer.dataProvider().addFeature(feature)
    layer.updateExtents()
    PROJECT.addMapLayer(layer, False)
    return layer


def finished_run(dock) -> None:
    pump(lambda: dock.run is None and dock.panel.run_button.isEnabled(), what="the run to end")


def start(dock) -> None:
    dock.panel.run_button.click()
    pump(lambda: dock.run is not None, what="the run to start")


def group(name: str):
    return PROJECT.layerTreeRoot().findGroup(name)


def qgis_loader() -> None:
    """QGIS's own plugin loader, on a copy made by the installer."""
    import install_plugin
    import qgis.utils

    folder = WORK / "plugins"
    install_plugin.install(folder)
    qgis.utils.plugin_paths[:] = [str(folder)]
    sys.path.insert(0, str(folder))
    for name in [name for name in sys.modules if name.startswith("wadi2d_qgis")]:
        del sys.modules[name]
    qgis.utils.updateAvailablePlugins()
    check("wadi2d_qgis" in qgis.utils.available_plugins, "QGIS's loader finds the installed plugin")
    check(qgis.utils.pluginMetadata("wadi2d_qgis", "name") == "Wadi2D", "QGIS reads metadata.txt")
    check(qgis.utils.loadPlugin("wadi2d_qgis"), "QGIS's loader imports it")
    check("wadi2d_qgis" in sys.modules, "from the installed copy")
    sys.path.remove(str(folder))
    for name in [name for name in sys.modules if name.startswith("wadi2d_qgis")]:
        del sys.modules[name]


def smoke() -> None:
    engine = f'"{sys.argv[1]}" "{HERE / "fake_engine.py"}"'
    settings.set_engine_text(engine)
    iface = Iface()

    dem_path = WORK / "dem.tif"
    fake_engine.write_tiff(dem_path, 500.0)
    dem = QgsRasterLayer(str(dem_path), "dem")
    check(dem.isValid(), "temporary raster layer is valid")
    PROJECT.addMapLayer(dem)
    iface.canvas.setLayers([dem])
    iface.canvas.setExtent(dem.extent())

    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    check(iface.icons and len(iface.menu) == 2, "toolbar button and menu entries added")
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    check(dock.isVisibleTo(iface.window), "dock opens from the toolbar button")
    pump(lambda: dock.schema is not None, what="the engine schema")
    check(dock.engine_label.text() == "Engine ready.", "schema read through the process wrapper")

    check(dock.terrain.dx.value() == 20.0, "cell size starts at 20")
    check(
        abs(dock.terrain.manning.value() - dock.schema.default("terrain.manning")) < 1e-9,
        "Manning from schema",
    )
    check(dock.panel.duration.value() == 1.0, "simulated time from schema")
    kinds = [dock.boundaries.kind.itemText(i) for i in range(dock.boundaries.kind.count())]
    check(kinds == ["stage", "normal", "free"], "boundary kinds from schema")
    check(dock.terrain.dem_layer().id() == dem.id(), "DEM combo lists the project raster")

    dialog = settings.EngineDialog(dock)
    dialog.check()
    pump(lambda: dialog.check_button.isEnabled(), what="the doctor")
    report = dialog.report.toPlainText()
    check(report.startswith("Engine found."), "doctor checks the engine")
    leaked = json.loads(report.split("\n", 1)[1])["qgis_env"]
    check(not any(leaked.values()), "the venv Python ran with QGIS's environment cleaned away")

    dock.hydrology.rain.setValue(25.0)
    dock.hydrology.hours.setValue(0.5)
    dock.panel.say("")
    dock.panel.folder.setFilePath("")
    dock.panel.run_button.click()
    check("output folder" in dock.panel.message.text(), "a missing folder is said in plain words")

    out = WORK / "study" / "run"
    dock.panel.folder.setFilePath(str(out))

    dock.panel.estimate_button.click()
    pump(lambda: "cells" in dock.panel.estimate_label.text(), what="the estimate")
    check(
        dock.panel.estimate_label.text() == "48 cells, 1.25 GB, about 4 min",
        "estimate shows cells, memory, time",
    )
    check(dock._scratch is None, "estimate left no temporary folder")

    values = dock._collect()
    check(values["crs"] == "EPSG:32640" and problems(values) == [], "job values collected from the dock")
    check(values["extent"] == (400000.0, 2699880.0, 400160.0, 2700000.0), "map extent inside the DEM")

    start_line = to_wgs84(400020.0, 2699940.0)
    end_line = to_wgs84(400140.0, 2699940.0)
    crest = line_layer("crest", "&field=crest:double", [start_line, end_line], "EPSG:4326", [512.5])
    z_wall = QgsGeometry.fromWkt("LineStringZ(400020 2699900 700, 400140 2699900 701)")
    spill = line_layer(
        "spill",
        "&field=crest:double&field=c:double&field=l:double",
        [QgsPointXY(400040, 2699960), QgsPointXY(400080, 2699960)],
        attributes=[510.0, 2.1, 40.0],
    )
    wall = line_layer("wall", "", z_wall, kind="LineStringZ")
    limit = line_layer(
        "limit",
        "&field=kind:string&field=value:double",
        [QgsPointXY(400000, 2699880), QgsPointXY(400160, 2699880)],
        attributes=["stage", 1.5],
    )
    ring = QgsGeometry.fromPolygonXY(
        [
            [
                QgsPointXY(400000, 2699880),
                QgsPointXY(400160, 2699880),
                QgsPointXY(400160, 2700000),
                QgsPointXY(400000, 2700000),
            ]
        ]
    )
    domain = line_layer("domain", "", ring, kind="Polygon")
    point = line_layer(
        "dam",
        "&field=name:string",
        QgsGeometry.fromPointXY(QgsPointXY(400080, 2699940)),
        attributes=["Dam 1"],
        kind="Point",
    )
    for layer in (crest, spill, wall, limit, domain, point):
        PROJECT.addMapLayer(layer)

    structures = dock.structures
    structures.layers["crest_line"].setLayer(crest)
    structures.fields["crest_line"]["crest_z"].setField("crest")
    structures.layers["spillway"].setLayer(spill)
    structures.fields["spillway"]["crest_z"].setField("crest")
    structures.fields["spillway"]["coefficient"].setField("c")
    structures.fields["spillway"]["length"].setField("l")
    structures.layers["wall"].setLayer(wall)
    dock.boundaries.layer.setLayer(limit)
    dock.terrain.domain.setLayer(domain)
    dock.points.layer.setLayer(point)
    dock.points.name.setField("name")
    dock.structures.setCollapsed(False)

    added: list[str] = []
    PROJECT.layersAdded.connect(lambda layers: added.extend(layer.name() for layer in layers))
    live_values: set[float] = set()
    probe = QgsPointXY(400030, 2699970)

    def watch_live() -> bool:
        layer = dock.live.layer()
        if layer is not None:
            value, good = layer.dataProvider().sample(probe, 1)
            if good:
                live_values.add(value)
        return dock.run is None and dock.panel.run_button.isEnabled()

    mode("ok")
    os.environ["WADI2D_FAKE_STEPS"] = "16"
    os.environ["WADI2D_FAKE_STEP_S"] = "0.2"
    start(dock)
    check(
        not dock.panel.run_button.isEnabled() and dock.panel.stop_button.isEnabled(), "buttons follow the run"
    )
    pump(watch_live, what="the good run")
    check(dock.panel.bar.value() == 100, "progress bar reaches 100")
    said = dock.panel.message.text()
    check(said == "Finished. point P1 is outside the domain.", "the warning stays on screen")
    status = dock.panel.status.text()
    check(
        all(word in status for word in ("of 1 h 00 min", "step 1.5 s", "wet cells", "mass error")),
        "status line",
    )

    job = json.loads((out / "job.json").read_text(encoding="utf-8"))
    check(
        Path(job["terrain"]["dem"]).is_absolute() and Path(job["grid"]["domain"]).is_absolute(),
        "paths absolute",
    )
    check(
        sorted(p.name for p in (out / "inputs").glob("*.geojson"))
        == [
            "boundaries.geojson",
            "crest_line.geojson",
            "design_points.geojson",
            "domain.geojson",
            "spillway.geojson",
            "wall.geojson",
        ],
        "every vector layer landed in inputs/ as GeoJSON",
    )
    crest_saved = json.loads((out / "inputs" / "crest_line.geojson").read_text(encoding="utf-8"))
    check(crest_saved["crs"]["properties"]["name"] == "EPSG:32640", "GeoJSON names the DEM CRS")
    x, y = crest_saved["features"][0]["geometry"]["coordinates"][0]
    check(
        abs(x - 400020.0) < 0.01 and abs(y - 2699940.0) < 0.01, "a WGS84 layer was reprojected to the DEM CRS"
    )
    objects = {entry["kind"]: entry for entry in job["terrain"]["objects"]}
    check(objects["crest_line"]["z_constant"] == 512.5, "crest elevation read from its field")
    check(
        objects["spillway"]["coefficient"] == 2.1 and objects["spillway"]["length"] == 40.0, "spillway fields"
    )
    check(objects["wall"]["z"] == [700.0, 701.0], "vertex Z of a 3D line kept")
    check(
        job["boundaries"][0]["kind"] == "stage" and job["boundaries"][0]["stage"] == 1.5,
        "per-line boundary fields",
    )
    check(
        job["outputs"]["points"] == [{"name": "Dam 1", "x": 400080.0, "y": 2699940.0}], "design point named"
    )
    check(job["storm"]["depth_mm"] == 12.5, "rain written as a depth")
    engines = [dock.panel.backend.itemData(i) for i in range(dock.panel.backend.count())]
    check(engines == dock.schema.enum("run.backend"), "the engine choices are the schema's")
    check("backend" not in job["run"], "the automatic engine leaves the job as it was")

    check(added.count("Wadi2D live depth") == 1, "live layer added exactly once")
    check(len(live_values) >= 3, f"live layer showed the rewrites in place: {sorted(live_values)}")
    os.environ["WADI2D_FAKE_STEP_S"] = "0.08"
    check(dock.live.layer() is None, "live layer leaves when the maps arrive")
    node = group("run")
    check(node is not None, "maps in a group named after the run")
    names = [child.name() for child in node.children()]
    check(names[:2] == ["max_depth", "hazard"] and len(names) == 6, "maps ordered, depth first")
    layers = {child.name(): child.layer() for child in node.children()}
    depth_renderer = layers["max_depth"].renderer()
    check(depth_renderer.type() == "singlebandpseudocolor", "depth styled")
    items = depth_renderer.shader().rasterShaderFunction().colorRampItemList()
    check(
        items[0].color.alpha() == 0 and items[-1].color.blue() > items[-1].color.red(),
        "ramp is transparent blue",
    )
    ramp = layers["hazard"].renderer().shader().rasterShaderFunction()
    check(len(ramp.colorRampItemList()) == 5, "hazard has its five classes")
    check(ramp.colorRampType() == QgsColorRampShader.Discrete, "hazard styled in classes")
    check(
        node.children()[0].isVisible() and not node.children()[1].itemVisibilityChecked(),
        "only depth switched on",
    )
    check(dock.panel.open_button.isVisibleTo(dock.panel), "Open results folder offered")

    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("cpu"))
    start(dock)
    check(not dock.panel.backend.isEnabled(), "the engine choice is held while it runs")
    finished_run(dock)
    check(
        (WORK / "study" / "run_2" / PROGRESS_FILE).is_file() and group("run_2"),
        "a second run never overwrites",
    )
    second_job = json.loads((WORK / "study" / "run_2" / "job.json").read_text(encoding="utf-8"))
    check(second_job["run"].get("backend") == "cpu", "a CPU choice reaches the job")
    dock.panel.backend.setCurrentIndex(dock.panel.backend.findData("auto"))

    mode("error")
    os.environ["WADI2D_FAKE_STEPS"] = "6"
    start(dock)
    finished_run(dock)
    said = dock.panel.message.text()
    check("numerically unstable" in said and "time step below the floor" in said, f"plain failure: {said}")
    check(dock.marker is not None, "failed cell marked on the map")
    centre = iface.canvas.center()
    check(abs(centre.x() - 400070.0) < 1.0 and abs(centre.y() - 2699950.0) < 1.0, "map centred on the cell")
    start(dock)
    check(dock.marker is None, "the marker goes with the next run")
    finished_run(dock)

    mode("refuse")
    start(dock)
    finished_run(dock)
    said = dock.panel.message.text()
    check(
        "refused" in said and "multiple of the DEM pixel" in said, f"exit 2 with the engine's reason: {said}"
    )

    mode("crash")
    start(dock)
    finished_run(dock)
    said = dock.panel.message.text()
    check("failed unexpectedly" in said and "before the first event" in said, f"exit 1 with stderr: {said}")

    mode("slow")
    os.environ["WADI2D_FAKE_STEPS"] = "400"
    start(dock)
    run_dir = dock.run.out_dir
    pump(lambda: dock.run.state.t > 0.0, what="the first step")
    dock.panel.stop_button.click()
    finished_run(dock)
    check(
        dock.panel.message.text() == "Stopped on request.",
        "Stop creates the file and exit 6 reads as stopped",
    )
    check(not (run_dir / STOP_FILE).exists(), "the engine took the stop file away")
    check(group(run_dir.name) is not None, "maps of a stopped run are loaded")

    mode("deaf")
    os.environ["WADI2D_FAKE_STEPS"] = "3"
    start(dock)
    deaf = dock.run
    deaf.stop_grace_ms = 800
    pump(lambda: deaf.pid is not None and deaf.state.t > 0.0, what="the deaf run")
    pid = deaf.pid
    dock.panel.stop_button.click()
    finished_run(dock)
    check("killed" in dock.panel.message.text(), "killed after the grace time, and it says so")
    pump(lambda: not pid_alive(pid), 10.0, "the process to die")
    say("the killed process is really gone")

    mode("slow")
    os.environ["WADI2D_FAKE_STEPS"] = "60"
    start(dock)
    run_dir = dock.run.out_dir
    pump(lambda: dock.run.state.t > 0.0 and dock.run.pid is not None, what="a run to outlive the plugin")
    pid = read_run_info(run_dir)["pid"]
    plugin.unload()
    pump(lambda: plugin.dock is None, what="the unload")
    for _ in range(20):
        QCoreApplication.processEvents()
        time.sleep(0.01)
    check(pid_alive(pid), "the engine survives the plugin being unloaded")
    check(not iface.icons and not iface.menu, "unload removes the button and the menu")

    second = wadi2d_qgis.classFactory(iface)
    second.initGui()
    check(second.dock is not None and second.dock.run is not None, "the next session re-attaches by itself")
    finished_run(second.dock)
    check(second.dock.panel.message.text().startswith("Finished."), "the attached run ends normally")
    check(group(run_dir.name) is not None, "the attached run's maps are loaded")
    check(not pid_alive(pid), "and its process is gone")

    dock = second.dock
    mode("ok")
    os.environ["WADI2D_FAKE_STEPS"] = "4"
    hms = WORK / "hms"
    hms.mkdir()
    (hms / "B.basin").write_text("Basin: B\n\nSubbasin: S1\nEnd:\n\nSubbasin: S2\nEnd:\n", "utf-8")
    (hms / "Storm.met").write_text("x", "utf-8")
    (hms / "C.control").write_text("x", "utf-8")
    dock.hydrology.folder.setFilePath(str(hms))
    check(dock.hydrology.table.rowCount() == 2, "subbasin table read from the basin file")
    check(dock.storm.kind.currentData() == "hms", "an HMS project brings its storm")
    dock.hydrology.table.cellWidget(1, 1).setCurrentText("2d")
    routing = dock.hydrology.routing
    schemes = [routing.itemData(i) for i in range(routing.count())]
    check(schemes == dock.schema.enum("hydrology.reach_routing"), "the reach routing choices are the engine's")
    check(routing.currentData() == dock.schema.default("hydrology.reach_routing"), "HMS-faithful routing by default")
    routing.setCurrentIndex(routing.findData("conserving"))
    dock.hydrology.setCollapsed(True)
    values = dock._collect()
    check("hms" in values, "a collapsed section still gives its HMS project")
    dock.hydrology.setCollapsed(False)
    start(dock)
    run_dir = dock.run.out_dir
    finished_run(dock)
    job = json.loads((run_dir / "job.json").read_text(encoding="utf-8"))
    check(job["storm"]["kind"] == "hypothetical", "the HMS storm comes through hms-import")
    modes = {entry["name"]: entry["mode"] for entry in job["hydrology"]["subbasins"]}
    check(modes == {"S1": "lumped", "S2": "2d"}, "lumped or 2D per subbasin")
    check(job["hydrology"]["reach_routing"] == "conserving", "the conserving reach routing survives the HMS merge")
    routing.setCurrentIndex(routing.findData("hms"))
    check(job["run"]["duration_s"] == 7200.0, "the HMS control file sets the simulated time")

    study_smoke(dock)

    settings.set_engine_text(r"C:\no\such\python.exe -m wadi2d.engine.cli")
    dock.schema = None
    dock.load_engine()
    pump(lambda: "not found" in dock.engine_label.text(), what="the missing engine message")
    check(not dock.panel.run_button.isEnabled(), "no engine, no Run")

    second.unload()


def study_smoke(dock) -> None:
    """The depth-area study through the dock and the process wrapper: progress, its table, a stop."""
    mode("ok")
    os.environ["WADI2D_FAKE_STEPS"] = "6"
    os.environ["WADI2D_FAKE_STEP_S"] = "0.2"
    across = line_layer(
        "across", "&field=name:string&field=area:double",
        [QgsPointXY(400020, 2699940), QgsPointXY(400140, 2699940)], attributes=["Outlet", 20.0],
    )  # fmt: skip
    PROJECT.addMapLayer(across)
    dock.points.layer.setLayer(across)
    dock.points.name.setField("name")
    dock.points.area.setField("area")
    box = dock.study
    check(box.spacing.currentData() == "bracket", "a study's storm areas bracket the drainage areas by default")
    check(not box.composite.isChecked(), "the composite map is off by default")
    box.start_button.click()
    pump(lambda: dock.study_run is not None, what="the study to start")
    check(not dock.panel.run_button.isEnabled() and not box.start_button.isEnabled(), "no run while a study runs")
    pump(lambda: "Run 1 of 2" in box.status.text(), what="the first run of the study")
    check("1 run left after it" in box.status.text(), f"the study says how many runs are left: {box.status.text()}")
    pump(lambda: dock.study_run is None, 60.0, "the study to end")
    check(box.table.rowCount() == 2 and box.table.item(0, 0).text() == "Outlet", "a table of design flows")
    check(box.message.text().startswith("Finished: 2 runs, 2 design flows"), f"the study ends: {box.message.text()}")
    label = box.file_label.text()
    check("design_points.csv" in label and "J1" in label, "where it is written, and the elements on the grid")
    job = json.loads((dock._study_dir / "job.json").read_text(encoding="utf-8"))
    check(job["arf"] == {"bracket": True}, "the study's job asks for bracketing storm areas")
    check(job["outputs"]["lines"][0]["drainage_area_km2"] == 20.0, "a line's drainage area from its field")
    check(dock.panel.run_button.isEnabled() and box.start_button.isEnabled(), "Run and Start study are back")

    mode("slow")
    os.environ["WADI2D_FAKE_STEPS"] = "400"
    box.start_button.click()
    pump(lambda: dock.study_run is not None, what="a slow study to start")
    follow = dock.study_run
    pump(lambda: follow.state.run is not None and follow.state.run.t > 0.0, what="the first run of a slow study")
    box.stop_button.click()
    pump(lambda: dock.study_run is None, 60.0, "the stopped study")
    said = box.message.text()
    check(said.startswith("Stopped after 0 of 2 runs") and "no design table" in said, f"a stopped study: {said}")
    check(box.table.rowCount() == 0 and box.start_button.isEnabled(), "no table, and a study can start again")
    os.environ["WADI2D_FAKE_STEP_S"] = "0.08"
    mode("ok")
    dock.points.layer.setLayer(None)


def real_engine() -> None:
    """The same dock against the real CLI: a job it accepts, an estimate, a run, a stop."""
    import numpy as np
    from osgeo import gdal, osr

    os.chdir(WORK)  # QGIS's working folder is not the repo: the engine must resolve from anywhere
    settings.set_engine_text(f'"{sys.argv[1]}" -m wadi2d.engine.cli')
    iface = Iface()
    size, pixel, west, north = 400, 5.0, 400000.0, 2702000.0
    east, south = west + size * pixel, north - size * pixel
    dem_path = WORK / "plane.tif"
    raster = gdal.GetDriverByName("GTiff").Create(str(dem_path), size, size, 1, gdal.GDT_Float32)
    raster.SetGeoTransform((west, pixel, 0.0, north, 0.0, -pixel))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32640)
    raster.SetProjection(srs.ExportToWkt())
    raster.GetRasterBand(1).WriteArray(120.0 - 0.01 * pixel * np.tile(np.arange(size), (size, 1)))
    raster = None
    dem = QgsRasterLayer(str(dem_path), "plane")
    check(dem.isValid(), "real: synthetic plane loaded")
    PROJECT.addMapLayer(dem)
    iface.canvas.setLayers([dem])
    iface.canvas.setExtent(dem.extent())
    outfall = line_layer("outfall", "", [QgsPointXY(east - 10, north), QgsPointXY(east - 10, south)])
    PROJECT.addMapLayer(outfall)

    plugin = wadi2d_qgis.classFactory(iface)
    plugin.initGui()
    plugin.toggle_action.setChecked(True)
    dock = plugin.dock
    pump(lambda: dock.schema is not None, 60.0, "the real schema")
    check(dock.terrain.dx.value() == 20.0, "real: the dock takes its defaults from wadi2d schema")
    dock.hydrology.rain.setValue(100.0)
    dock.hydrology.hours.setValue(0.2)
    dock.panel.duration.setValue(0.25)
    dock.boundaries.layer.setLayer(outfall)
    dock.boundaries.kind.setCurrentText("free")
    dock.panel.folder.setFilePath(str(WORK / "real" / "first"))

    dock.panel.estimate_button.click()
    pump(lambda: dock.panel.estimate_label.text() not in ("", "Estimating..."), 120.0, "the real estimate")
    said = dock.panel.estimate_label.text()
    check(said.startswith("10,000 cells") and "GB" in said, f"real: dry run reads {said}")

    start(dock)
    run_dir = dock.run.out_dir
    pump(lambda: dock.run is None and dock.panel.run_button.isEnabled(), 180.0, "the real run")
    said = dock.panel.message.text()
    check(said == "Finished.", f"real: {said} {dock.panel.status.text()}")
    check(dock.panel.bar.value() == 100, "real: progress bar reaches 100")
    status = dock.panel.status.text()
    check("0 h 15 min of 0 h 15 min" in status and "wet area" in status, f"real: {status}")
    check("mass error" in status, "real: mass error reported")
    node = group(run_dir.name)
    names = [child.name() for child in node.children()]
    check({"max_depth", "hazard", "max_speed", "arrival"} <= set(names), f"real: maps loaded {names}")
    depth = next(n.layer() for n in node.findLayers() if n.layer().name() == "max_depth")
    check(depth.name() == "max_depth", "real: depth on top")
    check(depth.renderer().type() == "singlebandpseudocolor", "real: depth styled")
    peak = depth.dataProvider().bandStatistics(1).maximumValue
    check(0.0 < peak < 5.0, f"real: a believable peak depth, {peak:.3f} m")

    dock.panel.folder.setFilePath(str(WORK / "real" / "stopped"))
    dock.panel.duration.setValue(dock.panel.duration.maximum())
    start(dock)
    run_dir = dock.run.out_dir
    live_seen: list[bool] = []

    def stepping() -> bool:
        live_seen.append(dock.live.layer() is not None)
        return dock.run.state.t > 0.0 and any(live_seen)

    pump(stepping, 120.0, "the real run to step and show its live layer")
    check(True, "real: live/depth.tif on the map while it runs")
    dock.panel.stop_button.click()
    pump(lambda: dock.run is None and dock.panel.run_button.isEnabled(), 120.0, "the real stop")
    check(dock.panel.message.text() == "Stopped on request.", f"real: {dock.panel.message.text()}")
    check(group(run_dir.name) is not None, "real: a stopped run still gives its maps")
    plugin.unload()


if __name__ == "__main__":
    try:
        if sys.argv[2:] == ["real"]:
            real_engine()
        else:
            qgis_loader()
            wadi2d_qgis = importlib.import_module("wadi2d_qgis")
            settings = importlib.import_module("wadi2d_qgis.settings")
            smoke()
        print("SMOKE PASSED", flush=True)
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.stdout.flush()
    os._exit(0)  # QGIS's own teardown is not what this test is about
